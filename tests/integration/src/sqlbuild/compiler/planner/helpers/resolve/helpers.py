"""Helpers for resolve integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationTarget,
    CompileModelConfig,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlReferenceKind
from sqlbuild.compiler.planner.helpers.resolve.resolve import resolve_model_sql
from sqlbuild.compiler.planner.models import BackfillResult, WarehouseSnapshot
from sqlbuild.compiler.planner.types import BackfillAction
from sqlbuild.spec.models.source import SourceEntry


def build_model(
    *,
    name: str,
    query_sql: str,
    config: dict[str, object],
    ref_names: tuple[str, ...],
) -> CompiledModel:
    """Build a minimal CompiledModel for resolve integration tests."""

    raw_schema: object | None = config.get("schema")
    schema: str = raw_schema if isinstance(raw_schema, str) else "staging"
    references: tuple[CompileSqlReference, ...] = tuple(
        CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name=ref_name)
        for ref_name in ref_names
    )
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        deps=(),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        query_sql=query_sql,
        config=CompileModelConfig(values=config),
        target=CompiledRelationTarget(
            database=None,
            schema=schema,
            name=name,
            qualified_name=f"{schema}.{name}",
        ),
        references=references,
    )


@dataclass(frozen=True)
class _ResolveResult:
    """Result from resolve_and_execute."""

    resolved_sql: str
    rows: list[Any]
    column_types: dict[str, str]


def resolve_and_execute(
    *,
    model: CompiledModel,
    snapshot: WarehouseSnapshot,
    model_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    connection: Any,
    full_refresh: bool = False,
    start_cursor_override: str | None = None,
    end_cursor_override: str | None = None,
) -> _ResolveResult:
    """Resolve model SQL and execute it against a real connection."""

    resolved_sql: str = resolve_model_sql(
        model=model,
        snapshot=snapshot,
        model_targets=model_targets,
        seed_targets={},
        source_map=source_map,
        source_warehouse_columns=source_warehouse_columns,
        star_exclude_keyword="EXCLUDE",
        backfill=BackfillResult(action=BackfillAction.WARN_ONLY),
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
    )

    result: Any = connection.execute(resolved_sql)
    rows: list[Any] = result.fetchall()
    column_types: dict[str, str] = {desc[0]: str(desc[1]) for desc in result.description}
    return _ResolveResult(resolved_sql=resolved_sql, rows=rows, column_types=column_types)
