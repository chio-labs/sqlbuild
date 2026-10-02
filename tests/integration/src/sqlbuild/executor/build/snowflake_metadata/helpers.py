"""Offline Snowflake build harness whose catalog follows the DDL the build issues.

Data statements are accepted and ignored; only relation existence and columns are simulated, so
metadata round trips during a real compile, plan, and build can be counted without a warehouse.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineOptions, CompilePipelineResult
from sqlbuild.executor.build.models import BuildExecutionResult, BuildRuntimeParams
from sqlbuild.executor.pipeline.main.run import run_build_pipeline
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.contracts.models import ConnectionHooks
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import (
    FakeColumn,
    FakeRelation,
    OfflineSnowflakeAdapter,
    RecordingSnowflakeWarehouse,
)

_NAME: str = r'(?P<{group}>(?:"[^"]*"|[A-Za-z0-9_$]+)(?:\.(?:"[^"]*"|[A-Za-z0-9_$]+)){{0,2}})'
_CREATE_AS_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TRANSIENT\s+|TEMPORARY\s+)?(?P<kind>TABLE|VIEW)\s+"
    + _NAME.format(group="name")
    + r"\s+AS\s+(?P<query>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_CREATE_DEFINED_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TRANSIENT\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    + _NAME.format(group="name")
    + r"\s*\(",
    re.IGNORECASE | re.DOTALL,
)
_DROP_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*DROP\s+(?:TABLE|VIEW)\s+(?:IF\s+EXISTS\s+)?" + _NAME.format(group="name") + r"\s*$",
    re.IGNORECASE,
)
_RENAME_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*ALTER\s+(?:TABLE|VIEW)\s+"
    + _NAME.format(group="name")
    + r"\s+RENAME\s+TO\s+"
    + _NAME.format(group="other")
    + r"\s*$",
    re.IGNORECASE,
)
_SWAP_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*ALTER\s+TABLE\s+"
    + _NAME.format(group="name")
    + r"\s+SWAP\s+WITH\s+"
    + _NAME.format(group="other")
    + r"\s*$",
    re.IGNORECASE,
)
_ADD_COLUMN_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*ALTER\s+TABLE\s+"
    + _NAME.format(group="name")
    + r'\s+ADD\s+COLUMN\s+"?(?P<column>[A-Za-z0-9_]+)"?\s+(?P<type>.+?)\s*$',
    re.IGNORECASE,
)
_CREATE_SCHEMA_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*CREATE\s+SCHEMA\s+IF\s+NOT\s+EXISTS\s+" + _NAME.format(group="name") + r"\s*$",
    re.IGNORECASE,
)
_DESCRIBE_QUERY_PATTERN: re.Pattern[str] = re.compile(
    r"^SELECT \* FROM \(SELECT (?P<columns>.+?) FROM \S+\) AS __describe_source LIMIT 0$",
    re.DOTALL,
)
_RUNTIME_BOUNDS_PATTERN: re.Pattern[str] = re.compile(r"^SELECT MIN\([^)]*\), MAX\([^)]*\) FROM ")
_COPY_SOURCE_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*SELECT\s+\*\s+FROM\s+" + _NAME.format(group="source") + r"\s*$", re.IGNORECASE
)
_DEFAULT_COLUMNS: tuple[FakeColumn, ...] = (FakeColumn(name="ID", data_type="NUMBER"),)
_STATUS_DESCRIPTION: tuple[tuple[str], ...] = (("status",),)


type _Identity = tuple[str, str, str]
type _DdlAction = Callable[[re.Match[str]], frozenset[_Identity]]


@dataclass
class SimulatedSnowflakeWarehouse(RecordingSnowflakeWarehouse):
    """Recording warehouse whose relations follow CREATE, DROP, RENAME, SWAP, and ADD COLUMN."""

    model_columns: dict[str, tuple[FakeColumn, ...]] = field(default_factory=dict)
    ddl_events: list[tuple[int, frozenset[_Identity]]] = field(default_factory=list)

    def reset(self) -> None:
        """Forget recorded statements and simulated DDL events, keeping the catalog."""

        super().reset()
        with self._lock:
            self.ddl_events.clear()

    def set_model_columns(self, *, model: str, columns: tuple[FakeColumn, ...]) -> None:
        """Change the columns a model's CREATE ... AS statements produce."""

        with self._lock:
            self.model_columns[model.upper()] = columns

    def _answer(self, *, sql: str, params: tuple[object, ...]) -> tuple[list[tuple[Any, ...]], Any]:
        routes: tuple[tuple[re.Pattern[str], _DdlAction], ...] = (
            (_CREATE_AS_PATTERN, self._create_as),
            (_CREATE_DEFINED_PATTERN, self._create_defined),
            (_DROP_PATTERN, self._drop),
            (_RENAME_PATTERN, self._rename),
            (_SWAP_PATTERN, self._swap),
            (_ADD_COLUMN_PATTERN, self._add_column),
            (_CREATE_SCHEMA_PATTERN, self._create_schema),
        )
        pattern: re.Pattern[str]
        apply: _DdlAction
        for pattern, apply in routes:
            match: re.Match[str]
            for match in filter(None, (pattern.match(sql),)):
                with self._lock:
                    changed: frozenset[_Identity] = apply(match)
                    self.ddl_events.append((len(self.attempted_sql) - 1, changed))
                return [], _STATUS_DESCRIPTION
        described: tuple[re.Match[str], ...] = tuple(
            filter(None, (_DESCRIBE_QUERY_PATTERN.match(sql),))
        )
        description: re.Match[str]
        for description in described:
            return [], tuple(
                (column.strip().strip('"'),) for column in description.group("columns").split(",")
            )
        bounds: tuple[re.Match[str], ...] = tuple(
            filter(None, (_RUNTIME_BOUNDS_PATTERN.match(sql),))
        )
        for _ in bounds:
            return [self.cursor_values], (("min",), ("max",))
        return super()._answer(sql=sql, params=params)

    def _create_as(self, match: re.Match[str]) -> frozenset[_Identity]:
        identity: _Identity = self._parts(match.group("name"))
        copied: tuple[re.Match[str], ...] = tuple(
            filter(None, (_COPY_SOURCE_PATTERN.match(match.group("query")),))
        )
        sources: frozenset[_Identity] = frozenset(
            self._parts(copy.group("source")) for copy in copied
        )
        source_columns: tuple[tuple[FakeColumn, ...], ...] = tuple(
            fake.columns for fake in filter(lambda fake: _identity(fake) in sources, self.relations)
        )
        columns: tuple[FakeColumn, ...] = next(
            iter(source_columns), self._model_columns_for(name=identity[2])
        )
        table_type: str = ("BASE TABLE", "VIEW")[match.group("kind").upper() == "VIEW"]
        self._put(
            relation=FakeRelation(
                database=identity[0],
                schema=identity[1],
                name=identity[2],
                table_type=table_type,
                is_transient=True,
                columns=columns,
            )
        )
        return frozenset({identity})

    def _create_defined(self, match: re.Match[str]) -> frozenset[_Identity]:
        identity: _Identity = self._parts(match.group("name"))
        existing: tuple[FakeRelation, ...] = tuple(
            filter(lambda fake: _identity(fake) == identity, self.relations)
        )
        self._put(
            relation=next(
                iter(existing),
                FakeRelation(
                    database=identity[0],
                    schema=identity[1],
                    name=identity[2],
                    is_transient=True,
                    columns=_DEFAULT_COLUMNS,
                ),
            )
        )
        return frozenset({identity})

    def _drop(self, match: re.Match[str]) -> frozenset[_Identity]:
        identity: _Identity = self._parts(match.group("name"))
        self.replace_relations(
            relations=tuple(filter(lambda fake: _identity(fake) != identity, self.relations))
        )
        return frozenset({identity})

    def _rename(self, match: re.Match[str]) -> frozenset[_Identity]:
        origin: _Identity = self._parts(match.group("name"))
        destination: _Identity = self._parts(match.group("other"))
        self.replace_relations(
            relations=tuple(
                (fake, _moved(fake=fake, identity=destination))[_identity(fake) == origin]
                for fake in self.relations
            )
        )
        return frozenset({origin, destination})

    def _swap(self, match: re.Match[str]) -> frozenset[_Identity]:
        left: _Identity = self._parts(match.group("name"))
        right: _Identity = self._parts(match.group("other"))
        targets: dict[_Identity, _Identity] = {left: right, right: left}
        self.replace_relations(
            relations=tuple(
                _moved(fake=fake, identity=targets.get(_identity(fake), _identity(fake)))
                for fake in self.relations
            )
        )
        return frozenset({left, right})

    def _add_column(self, match: re.Match[str]) -> frozenset[_Identity]:
        identity: _Identity = self._parts(match.group("name"))
        added: FakeColumn = FakeColumn(name=match.group("column").upper(), data_type="TEXT")
        self.replace_relations(
            relations=tuple(
                (fake, replace(fake, columns=(*fake.columns, added)))[_identity(fake) == identity]
                for fake in self.relations
            )
        )
        return frozenset({identity})

    def _create_schema(self, match: re.Match[str]) -> frozenset[_Identity]:
        parts: tuple[str, ...] = tuple(
            part.strip('"').upper() for part in match.group("name").split(".")
        )
        scope: tuple[str, ...] = (self.current_database, *parts)[-2:]
        self.extra_schemas = self.extra_schemas | {(scope[0], scope[1])}
        return frozenset({(scope[0], scope[1], "")})

    def _put(self, *, relation: FakeRelation) -> None:
        identity: _Identity = _identity(relation)
        self.replace_relations(
            relations=(*filter(lambda fake: _identity(fake) != identity, self.relations), relation)
        )

    def _model_columns_for(self, *, name: str) -> tuple[FakeColumn, ...]:
        candidates: tuple[str, ...] = tuple(
            filter(lambda model: _model_owns(model=model, name=name), self.model_columns)
        )
        models: list[str] = sorted(candidates, key=_name_length, reverse=True)
        return next((self.model_columns[model] for model in models), _DEFAULT_COLUMNS)

    def _parts(self, name: str) -> _Identity:
        parts: tuple[str, ...] = tuple(part.strip('"').upper() for part in name.split("."))
        full: tuple[str, ...] = (self.current_database, self.current_database, *parts)[-3:]
        return full[0], full[1], full[2]


def _name_length(name: str) -> int:
    return len(name)


def _model_owns(*, model: str, name: str) -> bool:
    return name == model or name.startswith(f"{model}__")


def _identity(fake: FakeRelation) -> _Identity:
    return fake.database, fake.schema, fake.name


def _moved(*, fake: FakeRelation, identity: _Identity) -> FakeRelation:
    return replace(fake, database=identity[0], schema=identity[1], name=identity[2])


@dataclass(frozen=True)
class OfflineBuild:
    """One compiled, planned, and executed offline Snowflake build."""

    result: BuildExecutionResult
    statements: tuple[str, ...]
    ddl_events: tuple[tuple[int, frozenset[_Identity]], ...]


def build_offline_snowflake_project(
    *, project_dir: Path, warehouse: SimulatedSnowflakeWarehouse, max_concurrency: int
) -> OfflineBuild:
    """Compile, plan, and build ``project_dir`` through the build pipeline, offline."""

    adapter: OfflineSnowflakeAdapter = OfflineSnowflakeAdapter(warehouse=warehouse)
    inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    config: dict[str, object] = dict(inputs.project_config.connection)
    planned: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=inputs,
        adapter=adapter,
        options=CompilePipelineOptions(
            no_sql_validation=True, no_cache=True, connection_config=config
        ),
        hooks=ConnectionHooks(),
    )
    warehouse.reset()
    result: BuildExecutionResult = run_build_pipeline(
        plan=planned.plan_output,
        connection_config=config,
        adapter=adapter,
        settings=inputs.project_config.settings,
        runtime=BuildRuntimeParams(
            run_id="offline_build",
            runtime_dir=project_dir / "target",
            promotion_mode=TablePromotionMode(adapter.default_table_promotion_mode()),
            max_concurrency=max_concurrency,
        ),
    )
    return OfflineBuild(
        result=result,
        statements=tuple(warehouse.attempted_sql),
        ddl_events=tuple(warehouse.ddl_events),
    )


def information_schema_statements(build: OfflineBuild) -> tuple[str, ...]:
    """Return build statements that read INFORMATION_SCHEMA, which needs a running warehouse."""

    return tuple(
        filter(
            lambda statement: _INFORMATION_SCHEMA_PATTERN.search(statement) is not None,
            build.statements,
        )
    )


def column_reads_by_relation(build: OfflineBuild) -> dict[str, int]:
    """Count SHOW COLUMNS reads per relation the build inspected."""

    reads: tuple[re.Match[str], ...] = tuple(
        filter(None, (_SHOW_COLUMNS_RELATION.match(statement) for statement in build.statements))
    )
    return dict(Counter(read.group(1).replace('"', "") for read in reads))


def repeated_metadata_reads(build: OfflineBuild) -> tuple[str, ...]:
    """Return metadata statements re-issued with no DDL on their relation since the last issue."""

    last_read: dict[str, int] = {}
    repeated: list[str] = []
    index: int
    statement: str
    for index, statement in enumerate(build.statements):
        identities: tuple[_Identity, ...] = _metadata_identities(statement)
        identity: _Identity
        for identity in identities:
            previous: int = last_read.get(statement, -1)
            changed: bool = any(
                previous < event_index < index and identity in names
                for event_index, names in build.ddl_events
            )
            repeated.extend(statement for _ in range(int(previous >= 0 and not changed)))
            last_read[statement] = index
    return tuple(repeated)


def _metadata_identities(statement: str) -> tuple[_Identity, ...]:
    identities: list[_Identity] = []
    pattern: re.Pattern[str]
    to_identity: Callable[[re.Match[str]], _Identity]
    for pattern, to_identity in _METADATA_STATEMENTS:
        identities.extend(map(to_identity, filter(None, (pattern.match(statement),))))
    return tuple(identities)


def _show_columns_identity(match: re.Match[str]) -> _Identity:
    parts: list[str] = match.group("relation").replace('"', "").split(".")
    return parts[0], parts[1], parts[2]


def _show_relation_identity(match: re.Match[str]) -> _Identity:
    return match.group("database"), match.group("schema"), match.group("name")


def _show_schema_identity(match: re.Match[str]) -> _Identity:
    return match.group("database"), match.group("schema"), ""


_INFORMATION_SCHEMA_PATTERN: re.Pattern[str] = re.compile(r"information_schema", re.IGNORECASE)
_SHOW_COLUMNS_RELATION: re.Pattern[str] = re.compile(r"^SHOW COLUMNS IN (?:TABLE|VIEW) (\S+)$")
_METADATA_STATEMENTS: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], _Identity]], ...] = (
    (
        re.compile(r"^SHOW COLUMNS IN (?:TABLE|VIEW) (?P<relation>\S+)$"),
        _show_columns_identity,
    ),
    (
        re.compile(
            r"^SHOW TERSE (?:TABLES|VIEWS) LIKE '(?P<name>[^']*)' "
            r'IN SCHEMA "(?P<database>[^"]*)"\."(?P<schema>[^"]*)"$'
        ),
        _show_relation_identity,
    ),
    (
        re.compile(r"^SHOW SCHEMAS LIKE '(?P<schema>[^']*)' IN DATABASE \"(?P<database>[^\"]*)\"$"),
        _show_schema_identity,
    ),
)


ORDER_COLUMNS: tuple[FakeColumn, ...] = (
    FakeColumn(name="ORDER_ID", data_type="NUMBER", numeric_precision=38, numeric_scale=0),
    FakeColumn(name="ORDERED_AT", data_type="TIMESTAMP_NTZ", character_maximum_length=None),
    FakeColumn(name="AMOUNT", data_type="NUMBER", numeric_precision=10, numeric_scale=2),
)
ORDER_MODELS: tuple[str, ...] = ("ORDERS_TABLE", "ORDERS_VIEW", "ORDERS_MERGE", "ORDERS_DAILY")
_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders_platform"\n'
        'adapter = "snowflake"\n\n'
        "[connection]\n"
        'account = "example"\n'
        'user = "example"\n'
        'database = "analytics"\n'
        'schema = "marts"\n\n'
        "[connection.session_parameters]\n"
        "QUOTED_IDENTIFIERS_IGNORE_CASE = true\n\n"
        "[defaults]\n"
        'database = "analytics"\n'
        'materialized = "table"\n\n'
        "[path_defaults.marts]\n"
        'schema = "marts"\n'
    ),
    "sources/raw.yml": (
        "sources:\n"
        "  - name: raw_orders\n    description: Test source raw_orders.\n"
        "    database: analytics\n"
        "    schema: raw\n"
        "    table: orders\n"
        "    columns:\n"
        "      - name: order_id\n"
        "        type: NUMBER(38, 0)\n"
        "      - name: ordered_at\n"
        "        type: TIMESTAMP_NTZ\n"
        "      - name: amount\n"
        "        type: NUMBER(10, 2)\n"
    ),
    "models/marts/orders_table.sql": (
        "MODEL (description 'Test model orders_table.',\n  materialized table,\n);\n\n"
        'SELECT order_id, ordered_at, amount FROM __source("raw_orders")\n'
    ),
    "models/marts/orders_view.sql": (
        'MODEL (description "Test model orders_view.",'
        '\n  materialized view,\n);\n\nSELECT order_id, amount FROM __ref("orders_table")\n'
    ),
    "models/marts/orders_merge.sql": (
        "MODEL (description 'Test model orders_merge.',\n"
        "  materialized incremental,\n"
        "  incremental_strategy merge,\n"
        "  unique_key [order_id],\n"
        "  cursor ordered_at,\n"
        "  cursor_type timestamp,\n"
        "  cursor_grain day,\n"
        "  cursor_inputs (\n    raw_orders ordered_at,\n  ),\n"
        "  on_schema_change append_new_columns,\n"
        ");\n\n"
        'SELECT order_id, ordered_at, amount FROM __source("raw_orders")\n'
    ),
    "models/marts/orders_daily.sql": (
        "MODEL (description 'Test model orders_daily.',\n"
        "  materialized incremental,\n"
        "  incremental_strategy delete_insert,\n"
        "  incremental_mode microbatch,\n"
        "  microbatch_strategy watermark,\n"
        "  cursor ordered_at,\n"
        "  cursor_type timestamp,\n"
        "  cursor_grain day,\n"
        "  cursor_start '2026-01-01',\n"
        "  cursor_end '2026-01-04',\n"
        "  cursor_watermark_mode all,\n"
        "  cursor_inputs (\n    raw_orders (column ordered_at, roles [filter, watermark]),\n  ),\n"
        "  batch_size 1d,\n"
        ");\n\n"
        'SELECT order_id, ordered_at, amount FROM __source("raw_orders")\n'
    ),
}


def write_orders_project(*, project_dir: Path) -> None:
    """Write a table, a view, a merge incremental, and a three-day microbatch model."""

    relative: str
    content: str
    for relative, content in _PROJECT_FILES.items():
        path: Path = project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(content, encoding="utf-8")


def orders_warehouse() -> SimulatedSnowflakeWarehouse:
    """Return a simulated warehouse holding the raw orders source."""

    warehouse: SimulatedSnowflakeWarehouse = SimulatedSnowflakeWarehouse(
        relations=(
            FakeRelation(database="ANALYTICS", schema="RAW", name="ORDERS", columns=ORDER_COLUMNS),
        ),
        cursor_values=("2026-01-01 00:00:00.000", "2026-01-03 12:00:00.000"),
    )
    model: str
    for model in ORDER_MODELS:
        warehouse.set_model_columns(model=model, columns=ORDER_COLUMNS)
    return warehouse


def failed_models(build: OfflineBuild) -> tuple[str, ...]:
    """Return models that did not build successfully."""

    return tuple(
        result.model_name
        for result in filter(
            lambda result: result.status != ExecutionStatus.SUCCESS, build.result.model_results
        )
    )
