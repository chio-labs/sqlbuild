from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_record
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind


class FakeSourceFreshnessExecute:
    def __init__(self, *, rows: list[tuple[Any, ...]], read_error: Exception | None = None) -> None:
        self._rows: list[tuple[Any, ...]] = rows
        self._read_error: Exception | None = read_error

    def __call__(self, _connection: object, sql: str) -> Any:
        del sql
        if self._read_error is not None:
            raise self._read_error
        return _FakeResult(self._rows)


def freshness_table_relation_exists(
    connection: Any, *, database: str | None, schema: str | None, name: str
) -> bool:
    del connection, database, schema, name
    return True


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
    write_source_freshness_record(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="state_schema",
        record=previous_record,
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
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
    write_source_freshness_record(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema=schema,
        record=SourceFreshnessRecord(
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
        render_qualified_name=render_qualified_name,
        render_framework_type=render_framework_type,
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
