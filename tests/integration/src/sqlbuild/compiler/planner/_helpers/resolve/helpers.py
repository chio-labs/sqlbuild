"""Helpers for resolve integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationLocation,
    CompileModelConfig,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.resolve.resolve import resolve_model_sql
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CursorOverridePair,
    ModelCursorSnapshot,
    ModelPlanContext,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import SourceEntry


def build_model(
    *,
    name: str,
    query_sql: str,
    config: dict[str, object],
    ref_names: tuple[str, ...],
) -> CompiledModel:
    """Build a minimal CompiledModel for resolve integration tests."""

    raw_schema: object | None = config.get("schema")
    schema: str = cast(str, ("staging", raw_schema)[isinstance(raw_schema, str)])
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
        destination=CompiledRelationLocation(
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
    model_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    connection: Any,
    full_refresh: bool = False,
    start_cursor_override: str | None = None,
    end_cursor_override: str | None = None,
    replaces_relation: bool = False,
) -> _ResolveResult:
    """Resolve model SQL and execute it against a real connection."""

    resolved_sql: str = resolve_model_sql(
        adapter=DuckDbAdapter(),
        model=model,
        snapshot=snapshot,
        context=ModelPlanContext(
            model_locations=model_locations,
            models_by_name={},
            functions_by_name={},
            seed_locations={},
            function_locations={},
            source_map=source_map,
            source_warehouse_columns=source_warehouse_columns,
            star_exclude_keyword="EXCLUDE",
        ),
        backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
        full_refresh=full_refresh,
        cursor_overrides=CursorOverridePair(
            start_cursor_override=start_cursor_override,
            end_cursor_override=end_cursor_override,
        ),
        replaces_relation=replaces_relation,
    )

    result: Any = connection.execute(resolved_sql)
    rows: list[Any] = result.fetchall()
    column_types: dict[str, str] = {desc[0]: str(desc[1]) for desc in result.description}
    return _ResolveResult(resolved_sql=resolved_sql, rows=rows, column_types=column_types)


def build_empty_input_model(*, cursor_start: str | None) -> CompiledModel:
    """Build a delete_insert cursor model reading the raw_events source."""

    config: dict[str, object] = {
        "materialized": "incremental",
        "incremental_strategy": "delete_insert",
        "cursor": "event_time",
        "cursor_type": "timestamp",
        "cursor_inputs": {"raw_events": "event_time"},
        "cursor_start": cursor_start,
    }
    return build_model(
        name="fact_events",
        query_sql='SELECT event_id, event_time FROM __source("raw_events")',
        config=config,
        ref_names=(),
    )


def build_empty_input_snapshot(
    *,
    target_max: str | None,
    target_relation: str | None,
    existing_relations: dict[str, RelationInfo],
) -> WarehouseSnapshot:
    """Build a planning snapshot in which the raw_events cursor input has no rows."""

    return WarehouseSnapshot(
        existing_relations=existing_relations,
        cursor_snapshots={
            "fact_events": ModelCursorSnapshot(
                target_max=target_max,
                upstream_mins=(),
                upstream_maxes=(),
                target_relation=target_relation,
                expected_watermark_count=1,
                unavailable_watermark_tags=("fact_events__raw_events__max",),
                empty_input_names=("raw_events.event_time",),
            )
        },
    )


def raw_events_source_map() -> dict[str, SourceEntry]:
    """Return the raw_events source declaration."""

    return {"raw_events": SourceEntry(name="raw_events", schema="staging", table="raw_events")}


def fact_events_relation(*, schema: str) -> dict[str, RelationInfo]:
    """Return an existing fact_events table in one schema, keyed as the planner keys it."""

    return {
        "fact_events": RelationInfo(
            database=None, schema=schema, name="fact_events", relation_type="table"
        )
    }
