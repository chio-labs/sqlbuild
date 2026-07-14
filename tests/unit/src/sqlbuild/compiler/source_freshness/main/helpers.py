from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import MappingProxyType
from typing import Any

from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.source_freshness._helpers.sql import build_read_latest_sql
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_records
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
    SourceFreshnessRenderers,
)
from sqlbuild.spec.contracts.types import SourceFreshnessStrategy, SourceFreshnessValueKind


def state_table_exists_map(
    *,
    adapter: Any,
    connection: Any,
    state_database: str | None,
    state_schemas: tuple[str, ...],
) -> dict[str, bool]:
    """Build the freshness state-table existence map the planning entrypoint requires."""

    lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            (state_database, schema, SOURCE_FRESHNESS_TABLE_NAME) for schema in state_schemas
        ),
    )
    return {
        schema: lookup.exists(schema=schema, name=SOURCE_FRESHNESS_TABLE_NAME)
        for schema in state_schemas
    }


class FakeSourceFreshnessExecute:
    def __init__(self, *, rows: list[tuple[Any, ...]]) -> None:
        self._rows: list[tuple[Any, ...]] = rows
        self.executed_sql: list[str] = []

    def __call__(self, *, connection: object, sql: str) -> Any:
        del connection
        self.executed_sql.append(sql)
        return _FakeResult(self._rows)


class FailingSourceFreshnessExecute(FakeSourceFreshnessExecute):
    def __init__(self, *, read_error: Exception) -> None:
        super().__init__(rows=[])
        self._read_error = read_error

    def __call__(self, *, connection: object, sql: str) -> Any:
        del connection
        self.executed_sql.append(sql)
        raise self._read_error


class FakeSourceFreshnessWriteExecute:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def __call__(self, *, connection: Any, sql: str) -> None:
        del connection
        self.executed_sql.append(sql)


class _FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows: list[tuple[Any, ...]] = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


def render_qualified_name(*, database: str | None, schema: str | None, name: str) -> str | None:
    names_by_parts: dict[tuple[bool, bool], str | None] = {
        (True, False): None,
        (True, True): None,
        (False, True): f"{database}.{schema}.{name}",
        (False, False): f"{schema}.{name}",
    }
    return names_by_parts[(schema is None, database is not None)]


def render_read_latest_sql(*, database: str | None, schema: str) -> str:
    return build_read_latest_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )


def render_sentinel_read_latest_sql(*, database: str | None, schema: str) -> str:
    del database, schema
    return "SELECT 'sentinel latest source freshness sql'"


def render_create_source_freshness_index_sqls(
    *, database: str | None, schema: str
) -> tuple[str, ...]:
    del database, schema
    return ("CREATE INDEX sentinel_source_freshness_idx",)


def write_optional_previous_record(
    *,
    adapter: DuckDbAdapter,
    connection: Any,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    data_version: str | None,
) -> None:
    previous_record: SourceFreshnessRecord = SourceFreshnessRecord(
        source_name="raw.orders",
        target_database=None,
        target_schema=None,
        target_name=None,
        run_id="previous",
        strategy=SourceFreshnessStrategy.SQL.value,
        value_kind=SourceFreshnessValueKind.INTEGER.value,
        data_version=data_version or "",
        data_version_hash=source_freshness_data_version_hash(
            source_name="raw.orders",
            strategy=SourceFreshnessStrategy.SQL,
            value_kind=SourceFreshnessValueKind.INTEGER,
            data_version=data_version or "",
        ),
        observed_at=datetime(2026, 1, 15, 10, 0, 0),
    )
    _OPTIONAL_PREVIOUS_RECORD_WRITERS[data_version is not None](
        adapter,
        connection,
        render_qualified_name,
        render_framework_type,
        previous_record,
    )


def _write_previous_record(
    adapter: DuckDbAdapter,
    connection: Any,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    previous_record: SourceFreshnessRecord,
) -> None:
    write_source_freshness_records(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="state_schema",
        records=(previous_record,),
        renderers=SourceFreshnessRenderers(
            render_qualified_name=render_qualified_name,
            render_framework_type=render_framework_type,
            render_insert_records_sql=adapter.render_insert_source_freshness_records_sql,
        ),
    )


def _skip_previous_record(
    adapter: DuckDbAdapter,
    connection: Any,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    previous_record: SourceFreshnessRecord,
) -> None:
    del adapter, connection, render_qualified_name, render_framework_type, previous_record


_OPTIONAL_PREVIOUS_RECORD_WRITERS: MappingProxyType[
    bool,
    Callable[
        [
            DuckDbAdapter,
            Any,
            Callable[..., str | None],
            Callable[[FrameworkType], str],
            SourceFreshnessRecord,
        ],
        None,
    ],
] = MappingProxyType({False: _skip_previous_record, True: _write_previous_record})


def write_previous_record_to_schema(
    *,
    adapter: DuckDbAdapter,
    connection: Any,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    schema: str,
    source_name: str,
    data_version: str,
    observed_at: datetime = datetime(2026, 1, 15, 10, 0, 0),
) -> None:
    write_source_freshness_records(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema=schema,
        records=(
            SourceFreshnessRecord(
                source_name=source_name,
                target_database=None,
                target_schema=None,
                target_name=None,
                run_id="previous",
                strategy=SourceFreshnessStrategy.SQL.value,
                value_kind=SourceFreshnessValueKind.INTEGER.value,
                data_version=data_version,
                data_version_hash=source_freshness_data_version_hash(
                    source_name=source_name,
                    strategy=SourceFreshnessStrategy.SQL,
                    value_kind=SourceFreshnessValueKind.INTEGER,
                    data_version=data_version,
                ),
                observed_at=observed_at,
            ),
        ),
        renderers=SourceFreshnessRenderers(
            render_qualified_name=render_qualified_name,
            render_framework_type=render_framework_type,
            render_insert_records_sql=adapter.render_insert_source_freshness_records_sql,
        ),
    )


def source_freshness_identity(source_name: str) -> SourceFreshnessIdentity:
    return SourceFreshnessIdentity(
        source_name=source_name,
        target_database=None,
        target_schema=None,
        target_name=None,
    )


def downstream_deps_from_edges(
    edges: dict[str, tuple[str, ...]],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {}
    for raw_key, downstream in edges.items():
        compiled_downstream: list[CompiledObjectKey] = []
        for raw_downstream in downstream:
            compiled_downstream.append(compiled_key(raw_downstream))
        downstream_deps[compiled_key(raw_key)] = tuple(compiled_downstream)
    return downstream_deps


def compiled_key(raw: str) -> CompiledObjectKey:
    raw_type: str
    name: str
    raw_type, name = raw.split(":", 1)
    return CompiledObjectKey(resource_type=CompiledResourceType(raw_type), name=name)
