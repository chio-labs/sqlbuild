from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.shared.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.compiler.source_freshness.helpers.sql import build_read_latest_sql
from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_records
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)
from sqlbuild.shared.models import RelationLookup
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind


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
    def __init__(self, *, rows: list[tuple[Any, ...]], read_error: Exception | None = None) -> None:
        self._rows: list[tuple[Any, ...]] = rows
        self._read_error: Exception | None = read_error
        self.executed_sql: list[str] = []

    def __call__(self, _connection: object, sql: str) -> Any:
        self.executed_sql.append(sql)
        if self._read_error is not None:
            raise self._read_error
        return _FakeResult(self._rows)


class FakeSourceFreshnessWriteExecute:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def __call__(self, connection: Any, sql: str) -> None:
        del connection
        self.executed_sql.append(sql)


class _FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows: list[tuple[Any, ...]] = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


def render_qualified_name(*, database: str | None, schema: str | None, name: str) -> str | None:
    if schema is None:
        return None
    if database is not None:
        return f"{database}.{schema}.{name}"
    return f"{schema}.{name}"


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
    if data_version is None:
        return
    previous_record: SourceFreshnessRecord = SourceFreshnessRecord(
        source_name="raw.orders",
        target_database=None,
        target_schema=None,
        target_name=None,
        run_id="previous",
        strategy=SourceFreshnessStrategy.SQL.value,
        value_kind=SourceFreshnessValueKind.INTEGER.value,
        data_version=data_version,
        data_version_hash=source_freshness_data_version_hash(
            source_name="raw.orders",
            strategy=SourceFreshnessStrategy.SQL,
            value_kind=SourceFreshnessValueKind.INTEGER,
            data_version=data_version,
        ),
        observed_at=datetime(2026, 1, 15, 10, 0, 0),
    )
    write_source_freshness_records(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="state_schema",
        records=(previous_record,),
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
        render_insert_records_sql=adapter.render_insert_source_freshness_records_sql,
    )


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
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
        render_insert_records_sql=adapter.render_insert_source_freshness_records_sql,
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
    return {
        compiled_key(raw_key): tuple(compiled_key(raw_downstream) for raw_downstream in downstream)
        for raw_key, downstream in edges.items()
    }


def compiled_key(raw: str) -> CompiledObjectKey:
    raw_type: str
    name: str
    raw_type, name = raw.split(":", 1)
    return CompiledObjectKey(resource_type=CompiledResourceType(raw_type), name=name)
