"""Gather a frozen point-in-time warehouse snapshot for planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSeed,
    CompiledSource,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlReferenceKind
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.planner.models import ModelCursorSnapshot, WarehouseSnapshot
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.spec.models.source import SourceEntry

_CURSOR_BATCH_SIZE: int = 100


@dataclass(frozen=True)
class _CursorQuery:
    """One MIN or MAX query to execute against a relation."""

    tag: str
    relation: str
    cursor_column: str
    aggregate: str


@dataclass(frozen=True)
class _UpstreamCursorInfo:
    """Pre-resolved upstream cursor metadata for one ref."""

    tag_min: str
    tag_max: str
    relation: str
    cursor_column: str


@dataclass(frozen=True)
class _CursorModelInfo:
    """Pre-resolved cursor metadata for one incremental model."""

    model_name: str
    target_tag: str | None
    target_relation: str | None
    cursor_column: str
    upstreams: tuple[_UpstreamCursorInfo, ...]


def gather_warehouse_snapshot(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    execute: Any,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
    full_refresh: bool = False,
    start_cursor_override: str | None = None,
    end_cursor_override: str | None = None,
    on_progress: Callable[[str], None] | None = None,
    deferred_targets: dict[str, CompiledRelationTarget] | None = None,
) -> WarehouseSnapshot:
    """Gather relations, columns, and fingerprints for all target schemas."""

    database: str | None = _resolve_database(project)
    schemas: tuple[str, ...] = _collect_target_schemas(project)
    if not schemas:
        return WarehouseSnapshot()

    relations: dict[str, RelationInfo] = _gather_relations(
        adapter=adapter, connection=connection, database=database, schemas=schemas
    )
    columns: dict[str, tuple[ColumnInfo, ...]] = _gather_columns(
        adapter=adapter, connection=connection, database=database, schemas=schemas
    )
    fingerprints: dict[str, Fingerprint] = _gather_fingerprints(
        connection=connection, execute=execute, database=database, schemas=schemas
    )

    skip_cursors: bool = full_refresh or (
        start_cursor_override is not None and end_cursor_override is not None
    )
    cursor_snapshots: dict[str, ModelCursorSnapshot] = {}
    if not skip_cursors:
        cursor_snapshots = _gather_cursor_snapshots(
            project=project,
            connection=connection,
            execute=execute,
            existing_relations=relations,
            selected_keys=selected_keys,
            on_progress=on_progress,
            deferred_targets=deferred_targets,
        )

    return WarehouseSnapshot(
        existing_relations=relations,
        existing_columns=columns,
        fingerprints=fingerprints,
        cursor_snapshots=cursor_snapshots,
    )


def _resolve_database(project: CompiledProject) -> str | None:
    """Extract the database from the first model target that declares one."""

    model: CompiledModel
    for model in project.models:
        if model.target.database is not None:
            return model.target.database
    seed: CompiledSeed
    for seed in project.seeds:
        if seed.target.database is not None:
            return seed.target.database
    return None


def _collect_target_schemas(project: CompiledProject) -> tuple[str, ...]:
    """Collect distinct non-null target schemas from models and seeds."""

    schemas: set[str] = set()
    model: CompiledModel
    for model in project.models:
        if model.target.schema is not None:
            schemas.add(model.target.schema)
    seed: CompiledSeed
    for seed in project.seeds:
        if seed.target.schema is not None:
            schemas.add(seed.target.schema)
    return tuple(sorted(schemas))


def _gather_relations(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schemas: tuple[str, ...],
) -> dict[str, RelationInfo]:
    """Fetch all existing relations across target schemas."""

    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection, database=database, schemas=schemas
    )
    result: dict[str, RelationInfo] = {}
    relation: RelationInfo
    for relation in relations:
        if relation.name == FINGERPRINT_TABLE_NAME:
            continue
        result[relation.name] = relation
    return result


def _gather_columns(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schemas: tuple[str, ...],
) -> dict[str, tuple[ColumnInfo, ...]]:
    """Fetch column metadata for all relations across target schemas."""

    all_columns: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
        connection, database=database, schemas=schemas
    )
    return {name: cols for name, cols in all_columns.items() if name != FINGERPRINT_TABLE_NAME}


def _gather_fingerprints(
    *,
    connection: Any,
    execute: Any,
    database: str | None,
    schemas: tuple[str, ...],
) -> dict[str, Fingerprint]:
    """Read latest fingerprints across all target schemas."""

    merged: dict[str, Fingerprint] = {}
    schema: str
    for schema in schemas:
        fingerprint_set: FingerprintSet = read_latest_fingerprints(
            connection=connection, execute=execute, database=database, schema=schema
        )
        merged.update(fingerprint_set.fingerprints)
    return merged


def _gather_cursor_snapshots(
    *,
    project: CompiledProject,
    connection: Any,
    execute: Any,
    existing_relations: dict[str, RelationInfo],
    selected_keys: frozenset[CompiledObjectKey] | None,
    on_progress: Callable[[str], None] | None,
    deferred_targets: dict[str, CompiledRelationTarget] | None = None,
) -> dict[str, ModelCursorSnapshot]:
    """Gather cursor MIN/MAX values for selected incremental models."""

    model_map: dict[str, CompiledModel] = {m.name: m for m in project.models}
    source_map: dict[str, CompiledSource] = {s.name: s for s in project.sources}

    cursor_models: list[_CursorModelInfo] = _collect_cursor_models(
        project=project,
        model_map=model_map,
        source_map=source_map,
        existing_relations=existing_relations,
        selected_keys=selected_keys,
        deferred_targets=deferred_targets,
    )
    if not cursor_models:
        return {}

    queries: list[_CursorQuery] = _build_cursor_queries(cursor_models)
    results: dict[str, str] = _execute_cursor_queries_batched(
        queries=queries,
        connection=connection,
        execute=execute,
        on_progress=on_progress,
    )

    return _assemble_cursor_snapshots(cursor_models=cursor_models, results=results)


def _collect_cursor_models(
    *,
    project: CompiledProject,
    model_map: dict[str, CompiledModel],
    source_map: dict[str, CompiledSource],
    existing_relations: dict[str, RelationInfo],
    selected_keys: frozenset[CompiledObjectKey] | None,
    deferred_targets: dict[str, CompiledRelationTarget] | None = None,
) -> list[_CursorModelInfo]:
    """Identify selected incremental models and pre-resolve their cursor metadata."""

    selected_names: frozenset[str] | None = (
        frozenset(k.name for k in selected_keys) if selected_keys is not None else None
    )
    cursor_models: list[_CursorModelInfo] = []
    model: CompiledModel
    for model in project.models:
        if selected_keys is not None:
            model_key: CompiledObjectKey = CompiledObjectKey(
                resource_type=CompiledResourceType.MODEL, name=model.name
            )
            if model_key not in selected_keys:
                continue

        cursor_column: str | None = _get_config_str(model, "cursor")
        materialized: str | None = _get_config_str(model, "materialized")
        if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
            continue

        cursor_inputs: dict[str, str] = _get_cursor_inputs(model, cursor_column)

        target_tag: str | None = None
        target_relation: str | None = None
        if model.target.qualified_name is not None and model.name in existing_relations:
            target_tag = f"{model.name}__target__max"
            target_relation = model.target.qualified_name

        upstreams: list[_UpstreamCursorInfo] = []
        ref: CompileSqlReference
        for ref in model.references:
            upstream_cursor_col: str | None = cursor_inputs.get(ref.ref_name)
            if upstream_cursor_col is None:
                continue
            upstream_relation: str | None = _resolve_upstream_qualified_name(
                ref=ref,
                model_map=model_map,
                source_map=source_map,
                deferred_targets=deferred_targets,
                selected_names=selected_names,
            )
            if upstream_relation is None:
                continue
            upstream_exists: bool = ref.ref_name in existing_relations or (
                ref.ref_kind == SqlReferenceKind.SOURCE
            )
            if not upstream_exists:
                continue
            upstreams.append(
                _UpstreamCursorInfo(
                    tag_min=f"{model.name}__{ref.ref_name}__min",
                    tag_max=f"{model.name}__{ref.ref_name}__max",
                    relation=upstream_relation,
                    cursor_column=upstream_cursor_col,
                )
            )

        cursor_models.append(
            _CursorModelInfo(
                model_name=model.name,
                target_tag=target_tag,
                target_relation=target_relation,
                cursor_column=cursor_column,
                upstreams=tuple(upstreams),
            )
        )

    return cursor_models


def _build_cursor_queries(cursor_models: list[_CursorModelInfo]) -> list[_CursorQuery]:
    """Build the full list of MIN/MAX queries from cursor model metadata."""

    queries: list[_CursorQuery] = []
    info: _CursorModelInfo
    for info in cursor_models:
        if info.target_tag is not None and info.target_relation is not None:
            queries.append(
                _CursorQuery(
                    tag=info.target_tag,
                    relation=info.target_relation,
                    cursor_column=info.cursor_column,
                    aggregate="MAX",
                )
            )
        upstream: _UpstreamCursorInfo
        for upstream in info.upstreams:
            queries.append(
                _CursorQuery(
                    tag=upstream.tag_min,
                    relation=upstream.relation,
                    cursor_column=upstream.cursor_column,
                    aggregate="MIN",
                )
            )
            queries.append(
                _CursorQuery(
                    tag=upstream.tag_max,
                    relation=upstream.relation,
                    cursor_column=upstream.cursor_column,
                    aggregate="MAX",
                )
            )

    return queries


def _execute_cursor_queries_batched(
    *,
    queries: list[_CursorQuery],
    connection: Any,
    execute: Any,
    on_progress: Callable[[str], None] | None,
) -> dict[str, str]:
    """Execute cursor queries in UNION ALL batches and return tag -> value results."""

    results: dict[str, str] = {}
    total: int = len(queries)
    completed: int = 0

    batch_start: int = 0
    while batch_start < total:
        batch_end: int = min(batch_start + _CURSOR_BATCH_SIZE, total)
        batch: list[_CursorQuery] = queries[batch_start:batch_end]

        batch_results: dict[str, str] = _execute_cursor_batch(
            batch=batch, connection=connection, execute=execute
        )
        results.update(batch_results)

        completed = batch_end
        if on_progress is not None:
            on_progress(f"Gathering cursor bounds ({completed}/{total})")

        batch_start = batch_end

    return results


def _execute_cursor_batch(
    *,
    batch: list[_CursorQuery],
    connection: Any,
    execute: Any,
) -> dict[str, str]:
    """Execute one batch of cursor queries as a UNION ALL and return tag -> value."""

    if len(batch) == 1:
        query: _CursorQuery = batch[0]
        sql: str = (
            f"SELECT '{query.tag}' AS _tag, "
            f"CAST({query.aggregate}({query.cursor_column}) AS VARCHAR) AS _val "
            f"FROM {query.relation}"
        )
    else:
        parts: list[str] = []
        q: _CursorQuery
        for q in batch:
            parts.append(
                f"SELECT '{q.tag}' AS _tag, "
                f"CAST({q.aggregate}({q.cursor_column}) AS VARCHAR) AS _val "
                f"FROM {q.relation}"
            )
        sql = " UNION ALL ".join(parts)

    try:
        result: Any = execute(connection, sql)
    except Exception:
        return {}
    rows: list[Any] = result.fetchall()
    output: dict[str, str] = {}
    row: Any
    for row in rows:
        tag: str = str(row[0])
        val: str | None = row[1]
        if val is not None:
            output[tag] = str(val)
    return output


def _assemble_cursor_snapshots(
    *,
    cursor_models: list[_CursorModelInfo],
    results: dict[str, str],
) -> dict[str, ModelCursorSnapshot]:
    """Fan batch query results back into per-model cursor snapshots."""

    snapshots: dict[str, ModelCursorSnapshot] = {}
    info: _CursorModelInfo
    for info in cursor_models:
        target_max: str | None = results.get(info.target_tag) if info.target_tag else None

        upstream_mins: list[str] = []
        upstream_maxes: list[str] = []
        upstream: _UpstreamCursorInfo
        for upstream in info.upstreams:
            min_val: str | None = results.get(upstream.tag_min)
            max_val: str | None = results.get(upstream.tag_max)
            if min_val is not None:
                upstream_mins.append(min_val)
            if max_val is not None:
                upstream_maxes.append(max_val)

        snapshots[info.model_name] = ModelCursorSnapshot(
            target_max=target_max,
            upstream_mins=tuple(upstream_mins),
            upstream_maxes=tuple(upstream_maxes),
        )

    return snapshots


def _get_cursor_inputs(model: CompiledModel, cursor_column: str) -> dict[str, str]:
    """Resolve cursor column mapping per upstream ref.

    For single-input models without explicit cursor_inputs, the cursor column
    is applied to all ref/source dependencies. For multi-input models,
    cursor_inputs must be explicit.
    """

    raw: object | None = model.config.values.get("cursor_inputs")
    if isinstance(raw, dict):
        return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}
    return {ref.ref_name: cursor_column for ref in model.references}


def _resolve_upstream_qualified_name(
    *,
    ref: CompileSqlReference,
    model_map: dict[str, CompiledModel],
    source_map: dict[str, CompiledSource],
    deferred_targets: dict[str, CompiledRelationTarget] | None = None,
    selected_names: frozenset[str] | None = None,
) -> str | None:
    """Resolve a reference to a qualified relation name for cursor reads."""

    if ref.ref_kind == SqlReferenceKind.REF:
        is_selected: bool = selected_names is not None and ref.ref_name in selected_names
        if deferred_targets is not None and ref.ref_name in deferred_targets and not is_selected:
            return deferred_targets[ref.ref_name].qualified_name
        upstream_model: CompiledModel | None = model_map.get(ref.ref_name)
        if upstream_model is not None:
            return upstream_model.target.qualified_name
    elif ref.ref_kind == SqlReferenceKind.SOURCE:
        source: CompiledSource | None = source_map.get(ref.ref_name)
        if source is not None:
            entry: SourceEntry = source.source_entry
            parts: list[str] = []
            if entry.database is not None:
                parts.append(entry.database)
            if entry.schema is not None:
                parts.append(entry.schema)
            table_name: str = entry.table if entry.table is not None else entry.name
            parts.append(table_name)
            return ".".join(parts)
    return None


def _get_config_str(model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None
