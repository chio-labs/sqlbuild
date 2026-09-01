"""Gather a frozen point-in-time warehouse snapshot for planning."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.compile.main._cursor_roles import resolve_cursor_input_roles
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import (
    FINGERPRINT_TABLE_NAME,
    FUNCTION_NODE_TYPES,
    NODE_TYPE_MODEL,
    NODE_TYPE_SEED,
)
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.planner._helpers.graph.buildability import check_buildability
from sqlbuild.compiler.planner._helpers.graph.core import build_execution_upstream_deps
from sqlbuild.compiler.planner._helpers.graph.loader_dag import (
    build_upstream_intermediate_source_map,
)
from sqlbuild.compiler.planner._helpers.planning.full_refresh import (
    effectively_full_refreshed_model_names,
)
from sqlbuild.compiler.planner.constants import METADATA_NAME_FILTER_LIMIT
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    MissingUpstream,
    ModelCursorSnapshot,
    PlannerScope,
    WarehouseFingerprints,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import ContractPolicy, MaterializationType
from sqlbuild.compiler.references.main._render_source_relation import render_source_relation
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.spec.contracts.models import SourceEntry

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.planner")


@dataclass(frozen=True)
class _PhysicalCursorQuery:
    """One physical relation and cursor column to inspect."""

    relation: str
    cursor_column: str
    min_tags: tuple[str, ...]
    max_tags: tuple[str, ...]


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


def build_warehouse_snapshot(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    full_refresh: bool = False,
    on_progress: Callable[[str], None] | None = None,
    deferred_locations: dict[str, CompiledRelationLocation] | None = None,
    deferred_relations: dict[str, RelationInfo] | None = None,
) -> WarehouseSnapshot:
    """Gather warehouse state and validate selected upstream availability."""

    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=adapter.execute,
        selected_keys=scope.selected_keys,
        full_refresh_model_names=effectively_full_refreshed_model_names(
            project=project,
            cli_full_refresh=full_refresh,
        ),
        on_progress=on_progress,
        deferred_locations=deferred_locations,
    )
    missing: tuple[MissingUpstream, ...] = check_buildability(
        selected_keys=scope.selected_keys,
        upstream_deps=scope.upstream_deps,
        snapshot=snapshot,
        deferred_relations=deferred_relations,
        satisfied_keys=frozenset(seed.key for seed in project.seeds if seed.external),
    )
    if missing:
        names: str = ", ".join(m.key.name for m in missing[:5])
        raise PlannerInputError(
            f"cannot build selected scope: {len(missing)} missing upstream dependencies ({names})",
            code="S301",
        )
    return snapshot


def gather_warehouse_snapshot(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    selected_keys: frozenset[CompiledObjectKey] | None = None,
    full_refresh: bool = False,
    full_refresh_model_names: frozenset[str] | None = None,
    on_progress: Callable[[str], None] | None = None,
    deferred_locations: dict[str, CompiledRelationLocation] | None = None,
    runtime_producer_keys: frozenset[CompiledObjectKey] | None = None,
) -> WarehouseSnapshot:
    """Gather relations, columns, and fingerprints for all target schemas."""

    relevant_keys: frozenset[CompiledObjectKey] | None = _relevant_state_keys(
        project=project,
        selected_keys=selected_keys,
    )
    database: str | None = _resolve_database(project=project, selected_keys=relevant_keys)
    schemas: tuple[str, ...] = _collect_target_schemas(project=project, selected_keys=relevant_keys)
    metadata_names: tuple[str, ...] | None = _build_metadata_name_filter(
        project=project,
        selected_keys=relevant_keys,
    )
    if not schemas and metadata_names is None:
        return WarehouseSnapshot()
    query_schemas: tuple[str, ...] | None = schemas or None

    relations: dict[str, RelationInfo]
    fingerprint_state_schemas: frozenset[str]
    freshness_state_schemas: frozenset[str]
    relations, fingerprint_state_schemas, freshness_state_schemas = _gather_relations(
        project=project,
        adapter=adapter,
        connection=connection,
        database=database,
        schemas=query_schemas,
        names=metadata_names,
    )
    columns: dict[str, tuple[ColumnInfo, ...]] = _gather_columns(
        adapter=adapter,
        connection=connection,
        relations=relations,
    )
    fingerprints: WarehouseFingerprints = _gather_fingerprints(
        adapter=adapter,
        connection=connection,
        execute=execute,
        database=database,
        schemas=query_schemas,
        fingerprint_state_schemas=fingerprint_state_schemas,
        node_names=_selected_node_names(relevant_keys),
    )

    effective_full_refresh_names: frozenset[str] = (
        full_refresh_model_names
        if full_refresh_model_names is not None
        else effectively_full_refreshed_model_names(
            project=project,
            cli_full_refresh=full_refresh,
        )
    )
    cursor_snapshots: dict[str, ModelCursorSnapshot] = _gather_cursor_snapshots(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=execute,
        existing_relations=relations,
        selected_keys=selected_keys,
        full_refresh_model_names=effective_full_refresh_names,
        on_progress=on_progress,
        deferred_locations=deferred_locations,
        runtime_producer_keys=runtime_producer_keys,
    )

    return WarehouseSnapshot(
        existing_relations=relations,
        existing_columns=columns,
        fingerprints=fingerprints,
        cursor_snapshots=cursor_snapshots,
        source_freshness_state_schemas=freshness_state_schemas,
    )


def _relevant_state_keys(
    *,
    project: CompiledProject,
    selected_keys: frozenset[CompiledObjectKey] | None,
) -> frozenset[CompiledObjectKey] | None:
    """Retain state identities for the complete upstream closure of the selection."""

    if selected_keys is None:
        return None
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(project)
    )
    closure: set[CompiledObjectKey] = set(selected_keys)
    pending: list[CompiledObjectKey] = list(selected_keys)
    while pending:
        key: CompiledObjectKey = pending.pop()
        upstream_key: CompiledObjectKey
        for upstream_key in upstream_deps.get(key, ()):
            if upstream_key not in closure:
                closure.add(upstream_key)
                pending.append(upstream_key)
    return frozenset(closure)


def _resolve_database(
    *,
    project: CompiledProject,
    selected_keys: frozenset[CompiledObjectKey] | None,
) -> str | None:
    """Extract the database from the first model target that declares one."""

    model: CompiledModel
    for model in project.models:
        if selected_keys is not None and model.key not in selected_keys:
            continue
        if model.destination.database is not None:
            return model.destination.database
    seed: CompiledSeed
    for seed in project.seeds:
        if selected_keys is not None and seed.key not in selected_keys:
            continue
        if seed.destination.database is not None:
            return seed.destination.database
    function: CompiledFunction
    for function in project.functions:
        if selected_keys is not None and function.key not in selected_keys:
            continue
        if function.destination.database is not None:
            return function.destination.database
    return project.effective_target_database


def _collect_target_schemas(
    *,
    project: CompiledProject,
    selected_keys: frozenset[CompiledObjectKey] | None,
) -> tuple[str, ...]:
    """Collect distinct non-null target schemas from models, seeds, and functions."""

    schemas: set[str] = set()
    model: CompiledModel
    for model in project.models:
        if selected_keys is not None and model.key not in selected_keys:
            continue
        if model.destination.schema is not None:
            schemas.add(model.destination.schema)
    seed: CompiledSeed
    for seed in project.seeds:
        if selected_keys is not None and seed.key not in selected_keys:
            continue
        if seed.destination.schema is not None:
            schemas.add(seed.destination.schema)
    function: CompiledFunction
    for function in project.functions:
        if selected_keys is not None and function.key not in selected_keys:
            continue
        if function.destination.schema is not None:
            schemas.add(function.destination.schema)
    if not schemas and project.effective_target_schema is not None:
        schemas.add(project.effective_target_schema)
    return tuple(sorted(schemas))


def _build_metadata_name_filter(
    *,
    project: CompiledProject,
    selected_keys: frozenset[CompiledObjectKey] | None,
) -> tuple[str, ...] | None:
    names: set[str] = set()
    if selected_keys is None:
        model: CompiledModel
        for model in project.models:
            names.add(model.destination.name)
        seed: CompiledSeed
        for seed in project.seeds:
            names.add(seed.destination.name)
    else:
        selected_names: frozenset[str] = frozenset(key.name for key in selected_keys)
        model_map: dict[str, CompiledModel] = {model.name: model for model in project.models}
        seed_map: dict[str, CompiledSeed] = {seed.name: seed for seed in project.seeds}
        source_map: dict[str, SourceEntry] = {
            source.source_entry.name: source.source_entry for source in project.sources
        }
        key: CompiledObjectKey
        for key in selected_keys:
            selected_model: CompiledModel | None = model_map.get(key.name)
            if selected_model is not None:
                names.add(selected_model.destination.name)
                names.update(
                    _model_upstream_names(
                        model=selected_model,
                        model_map=model_map,
                        seed_map=seed_map,
                        selected_names=selected_names,
                    )
                )
                continue
            selected_seed: CompiledSeed | None = seed_map.get(key.name)
            if selected_seed is not None:
                names.add(selected_seed.destination.name)
                continue
            selected_source: SourceEntry | None = source_map.get(key.name)
            if selected_source is not None:
                names.add(selected_source.table or selected_source.name)
        upstream_intermediate_source: SourceEntry
        for upstream_intermediate_source in build_upstream_intermediate_source_map(
            project=project,
            selected_keys=selected_keys,
        ).values():
            names.add(upstream_intermediate_source.table or upstream_intermediate_source.name)
    if not names or len(names) > METADATA_NAME_FILTER_LIMIT:
        return None
    names.add(FINGERPRINT_TABLE_NAME)
    names.add(SOURCE_FRESHNESS_TABLE_NAME)
    return tuple(sorted(names))


def _model_upstream_names(
    *,
    model: CompiledModel,
    model_map: dict[str, CompiledModel],
    seed_map: dict[str, CompiledSeed],
    selected_names: frozenset[str],
) -> frozenset[str]:
    names: set[str] = set()
    reference: CompileSqlReference
    for reference in model.references:
        if (
            reference.ref_kind
            not in {
                SqlReferenceKind.REF,
                SqlReferenceKind.SEED,
            }
            or reference.ref_name in selected_names
        ):
            continue
        if reference.ref_kind == SqlReferenceKind.REF:
            upstream_model: CompiledModel | None = model_map.get(reference.ref_name)
            if upstream_model is not None:
                names.add(upstream_model.destination.name)
            continue
        if reference.ref_kind == SqlReferenceKind.SEED:
            upstream_seed: CompiledSeed | None = seed_map.get(reference.ref_name)
            if upstream_seed is not None:
                names.add(upstream_seed.destination.name)
            continue
    return frozenset(names)


def _gather_relations(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schemas: tuple[str, ...] | None,
    names: tuple[str, ...] | None,
) -> tuple[dict[str, RelationInfo], frozenset[str], frozenset[str]]:
    """Fetch relations and the schemas where the fingerprint/freshness state tables exist."""

    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection, database=database, schemas=schemas, names=names
    )
    result: dict[str, RelationInfo] = {}
    logical_names_by_identity: dict[tuple[str | None, str | None, str], str] = {}
    model: CompiledModel
    for model in project.models:
        logical_names_by_identity[_location_identity(model.destination)] = model.name
    seed: CompiledSeed
    for seed in project.seeds:
        logical_names_by_identity[_location_identity(seed.destination)] = seed.name
    function: CompiledFunction
    for function in project.functions:
        logical_names_by_identity[_location_identity(function.destination)] = function.name
    fingerprint_schemas: set[str] = set()
    freshness_schemas: set[str] = set()
    relation: RelationInfo
    for relation in relations:
        if relation.name == FINGERPRINT_TABLE_NAME:
            if relation.schema is not None:
                fingerprint_schemas.add(relation.schema.lower())
            continue
        if relation.name == SOURCE_FRESHNESS_TABLE_NAME:
            if relation.schema is not None:
                freshness_schemas.add(relation.schema.lower())
            continue
        result[logical_names_by_identity.get(relation.identity, relation.name)] = relation
    return result, frozenset(fingerprint_schemas), frozenset(freshness_schemas)


def _location_identity(
    location: CompiledRelationLocation,
) -> tuple[str | None, str | None, str]:
    return (
        None if location.database is None else location.database.lower(),
        None if location.schema is None else location.schema.lower(),
        location.name.lower(),
    )


def _gather_columns(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relations: dict[str, RelationInfo],
) -> dict[str, tuple[ColumnInfo, ...]]:
    """Fetch column metadata for all relations across target schemas."""

    physical_relations: tuple[RelationInfo, ...] = tuple(relations.values())
    all_columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        adapter.get_columns_for_relations(connection=connection, relations=physical_relations)
    )
    return {
        logical_name: all_columns[relation.identity]
        for logical_name, relation in relations.items()
        if relation.identity in all_columns
    }


def _gather_fingerprints(
    *,
    adapter: BaseAdapter,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    database: str | None,
    schemas: tuple[str, ...] | None,
    fingerprint_state_schemas: frozenset[str],
    node_names: tuple[str, ...] | None,
) -> WarehouseFingerprints:
    """Read latest fingerprints across all target schemas grouped by node type."""

    if schemas is None:
        return WarehouseFingerprints()
    model_fingerprints: dict[str, Fingerprint] = {}
    function_fingerprints: dict[str, Fingerprint] = {}
    seed_fingerprints: dict[str, Fingerprint] = {}
    python_fingerprints: dict[tuple[str, str], Fingerprint] = {}
    schema: str
    for schema in schemas:
        fingerprint_set: FingerprintSet = read_latest_fingerprints(
            connection=connection,
            execute=execute,
            table_exists=schema.lower() in fingerprint_state_schemas,
            database=database,
            schema=schema,
            render_qualified_name=adapter.render_qualified_name,
            render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
            node_names=node_names,
            filtered_node_types=(NODE_TYPE_MODEL, *FUNCTION_NODE_TYPES, NODE_TYPE_SEED),
        )
        node_name: str
        fingerprint: Fingerprint
        for node_name, fingerprint in fingerprint_set.fingerprints.items():
            if fingerprint.node_type == NODE_TYPE_MODEL:
                model_fingerprints[node_name] = fingerprint
            elif fingerprint.node_type in FUNCTION_NODE_TYPES:
                function_fingerprints[node_name] = fingerprint
            elif fingerprint.node_type == NODE_TYPE_SEED:
                seed_fingerprints[node_name] = fingerprint
        if fingerprint_set.fingerprints_by_identity is not None:
            identity_key: tuple[str, str]
            for identity_key, fingerprint in fingerprint_set.fingerprints_by_identity.items():
                if fingerprint.node_type not in {
                    NODE_TYPE_MODEL,
                    *FUNCTION_NODE_TYPES,
                    NODE_TYPE_SEED,
                }:
                    python_fingerprints[identity_key] = fingerprint
    return WarehouseFingerprints(
        models=model_fingerprints,
        functions=function_fingerprints,
        seeds=seed_fingerprints,
        python_nodes=python_fingerprints,
    )


def _selected_node_names(
    selected_keys: frozenset[CompiledObjectKey] | None,
) -> tuple[str, ...] | None:
    if selected_keys is None:
        return None
    return tuple(sorted({key.name for key in selected_keys}))


def _gather_cursor_snapshots(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    existing_relations: dict[str, RelationInfo],
    selected_keys: frozenset[CompiledObjectKey] | None,
    full_refresh_model_names: frozenset[str],
    on_progress: Callable[[str], None] | None,
    deferred_locations: dict[str, CompiledRelationLocation] | None = None,
    runtime_producer_keys: frozenset[CompiledObjectKey] | None = None,
) -> dict[str, ModelCursorSnapshot]:
    """Gather cursor MIN/MAX values for selected incremental models."""

    model_map: dict[str, CompiledModel] = {m.name: m for m in project.models}
    source_map: dict[str, CompiledSource] = {s.name: s for s in project.sources}

    cursor_models: list[_CursorModelInfo] = _collect_cursor_models(
        project=project,
        adapter=adapter,
        model_map=model_map,
        source_map=source_map,
        existing_relations=existing_relations,
        selected_keys=selected_keys,
        full_refresh_model_names=full_refresh_model_names,
        deferred_locations=deferred_locations,
        runtime_producer_keys=runtime_producer_keys,
    )
    if not cursor_models:
        return {}

    queries: list[_PhysicalCursorQuery] = _build_cursor_queries(cursor_models)
    cursor_start: float = time.monotonic()
    results: dict[str, str] = _execute_cursor_queries(
        queries=queries,
        connection=connection,
        execute=execute,
        on_progress=on_progress,
    )
    if on_progress is not None:
        logical_total: int = sum(len(query.min_tags) + len(query.max_tags) for query in queries)
        physical_total: int = len(queries)
        on_progress(
            f"Gathered cursor bounds ({len(results)}/{logical_total} logical values; "
            f"{physical_total} physical relation reads). ({time.monotonic() - cursor_start:.2f}s)"
        )

    return _assemble_cursor_snapshots(cursor_models=cursor_models, results=results)


def _collect_cursor_models(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    model_map: dict[str, CompiledModel],
    source_map: dict[str, CompiledSource],
    existing_relations: dict[str, RelationInfo],
    selected_keys: frozenset[CompiledObjectKey] | None,
    full_refresh_model_names: frozenset[str],
    deferred_locations: dict[str, CompiledRelationLocation] | None = None,
    runtime_producer_keys: frozenset[CompiledObjectKey] | None = None,
) -> list[_CursorModelInfo]:
    """Identify selected incremental models and pre-resolve their cursor metadata."""

    effective_runtime_producer_keys: frozenset[CompiledObjectKey] | None = (
        runtime_producer_keys if runtime_producer_keys is not None else selected_keys
    )
    selected_names: frozenset[str] | None = (
        frozenset(k.name for k in effective_runtime_producer_keys)
        if effective_runtime_producer_keys is not None
        else None
    )
    seed_map: dict[str, CompiledSeed] = {seed.name: seed for seed in project.seeds}
    runtime_producer_names: frozenset[str] = _selected_runtime_producer_names(
        project=project,
        selected_keys=effective_runtime_producer_keys,
    )
    cursor_models: list[_CursorModelInfo] = []
    model: CompiledModel
    for model in project.models:
        if model.name in full_refresh_model_names:
            continue
        if selected_keys is not None:
            model_key: CompiledObjectKey = CompiledObjectKey(
                resource_type=CompiledResourceType.MODEL, name=model.name
            )
            if model_key not in selected_keys:
                continue

        cursor_column: str | None = _get_config_str(model=model, key="cursor")
        materialized: str | None = _get_config_str(model=model, key="materialized")
        if materialized != MaterializationType.INCREMENTAL or cursor_column is None:
            continue

        cursor_watermark_inputs: dict[str, str] = resolve_cursor_input_roles(
            model=model
        ).watermark_inputs

        target_tag: str | None = None
        target_relation: str | None = None
        target_relation_info: RelationInfo | None = existing_relations.get(model.name)
        if (
            model.destination.qualified_name is not None
            and target_relation_info is not None
            and target_relation_info.name == model.name
        ):
            target_tag = f"{model.name}__target__max"
            target_relation = model.destination.qualified_name

        upstreams: list[_UpstreamCursorInfo] = []
        input_name: str
        upstream_cursor_col: str
        for input_name, upstream_cursor_col in cursor_watermark_inputs.items():
            ref: CompileSqlReference = _resolve_lineage_reference(
                model=model,
                input_name=input_name,
                model_map=model_map,
            )
            _validate_watermark_contract_column(
                model=model,
                ref=ref,
                cursor_column=upstream_cursor_col,
                model_map=model_map,
                source_map=source_map,
                seed_map=seed_map,
            )
            if ref.ref_name in runtime_producer_names:
                continue
            upstream_relation: str | None = _resolve_upstream_qualified_name(
                ref=ref,
                adapter=adapter,
                model_map=model_map,
                source_map=source_map,
                seed_map=seed_map,
                deferred_locations=deferred_locations,
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


def _build_cursor_queries(cursor_models: list[_CursorModelInfo]) -> list[_PhysicalCursorQuery]:
    """Group logical cursor requests by physical relation and column."""

    grouped_tags: dict[tuple[str, str], tuple[list[str], list[str]]] = {}
    info: _CursorModelInfo
    for info in cursor_models:
        if info.target_tag is not None and info.target_relation is not None:
            target_key: tuple[str, str] = (info.target_relation, info.cursor_column)
            target_tags: tuple[list[str], list[str]] = grouped_tags.setdefault(target_key, ([], []))
            if info.target_tag not in target_tags[1]:
                target_tags[1].append(info.target_tag)
        upstream: _UpstreamCursorInfo
        for upstream in info.upstreams:
            upstream_key: tuple[str, str] = (upstream.relation, upstream.cursor_column)
            upstream_tags: tuple[list[str], list[str]] = grouped_tags.setdefault(
                upstream_key, ([], [])
            )
            if upstream.tag_min not in upstream_tags[0]:
                upstream_tags[0].append(upstream.tag_min)
            if upstream.tag_max not in upstream_tags[1]:
                upstream_tags[1].append(upstream.tag_max)

    return [
        _PhysicalCursorQuery(
            relation=relation,
            cursor_column=cursor_column,
            min_tags=tuple(tags[0]),
            max_tags=tuple(tags[1]),
        )
        for (relation, cursor_column), tags in grouped_tags.items()
    ]


def _execute_cursor_queries(
    *,
    queries: list[_PhysicalCursorQuery],
    connection: Any,
    execute: AdapterExecute[Any, Any],
    on_progress: Callable[[str], None] | None,
) -> dict[str, str]:
    """Execute standalone physical cursor queries and fan values out to logical tags."""

    results: dict[str, str] = {}
    total: int = len(queries)
    query_index: int
    query: _PhysicalCursorQuery
    for query_index, query in enumerate(queries, start=1):
        query_results: dict[str, str] = _execute_cursor_query(
            query=query,
            query_index=query_index,
            total=total,
            connection=connection,
            execute=execute,
            on_progress=on_progress,
        )
        results.update(query_results)

    return results


def _execute_cursor_query(
    *,
    query: _PhysicalCursorQuery,
    query_index: int,
    total: int,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    on_progress: Callable[[str], None] | None,
) -> dict[str, str]:
    """Execute one physical cursor query and fan out its returned values."""

    bounds: str = ",".join(("min",) if query.min_tags else ())
    if query.max_tags:
        bounds = f"{bounds},max" if bounds else "max"
    identity: str = f"({query_index}/{total}): {query.relation}.{query.cursor_column} [{bounds}]"
    select_parts: list[str] = []
    if query.min_tags:
        select_parts.append(f"CAST(MIN({query.cursor_column}) AS VARCHAR) AS _min")
    if query.max_tags:
        select_parts.append(f"CAST(MAX({query.cursor_column}) AS VARCHAR) AS _max")
    sql: str = f"SELECT {', '.join(select_parts)} FROM {query.relation}"
    if on_progress is not None:
        on_progress(f"Inspecting cursor bounds {identity}...")

    query_start: float = time.monotonic()
    try:
        result: Any = execute(connection=connection, sql=sql)
        rows: list[Any] = result.fetchall()
    except Exception as error:
        elapsed: float = time.monotonic() - query_start
        if on_progress is not None:
            on_progress(f"Failed cursor bounds {identity} ({elapsed:.2f}s): {error}")
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="cursor bounds physical query failed; treating relation as unavailable",
            sqlbuild_relation=query.relation,
            sqlbuild_cursor_column=query.cursor_column,
            sqlbuild_bounds=bounds,
            sqlbuild_elapsed_seconds=f"{elapsed:.2f}",
            sqlbuild_error=str(error),
        )
        return {}
    elapsed = time.monotonic() - query_start
    if on_progress is not None:
        on_progress(f"Inspected cursor bounds {identity} ({elapsed:.2f}s)")
    if not rows:
        return {}
    output: dict[str, str] = {}
    row: Any = rows[0]
    value_index: int = 0
    if query.min_tags:
        min_value: Any = row[value_index]
        if min_value is not None:
            min_tag: str
            for min_tag in query.min_tags:
                output[min_tag] = str(min_value)
        value_index += 1
    if query.max_tags:
        max_value: Any = row[value_index]
        if max_value is not None:
            max_tag: str
            for max_tag in query.max_tags:
                output[max_tag] = str(max_value)
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
        unavailable_watermark_tags: list[str] = []
        upstream: _UpstreamCursorInfo
        for upstream in info.upstreams:
            min_val: str | None = results.get(upstream.tag_min)
            max_val: str | None = results.get(upstream.tag_max)
            if min_val is not None:
                upstream_mins.append(min_val)
            elif target_max is None:
                unavailable_watermark_tags.append(upstream.tag_min)
            if max_val is not None:
                upstream_maxes.append(max_val)
            else:
                unavailable_watermark_tags.append(upstream.tag_max)

        snapshots[info.model_name] = ModelCursorSnapshot(
            target_max=target_max,
            upstream_mins=tuple(upstream_mins),
            upstream_maxes=tuple(upstream_maxes),
            expected_watermark_count=len(info.upstreams),
            unavailable_watermark_tags=tuple(unavailable_watermark_tags),
        )

    return snapshots


def _resolve_upstream_qualified_name(
    *,
    ref: CompileSqlReference,
    adapter: BaseAdapter,
    model_map: dict[str, CompiledModel],
    source_map: dict[str, CompiledSource],
    seed_map: dict[str, CompiledSeed],
    deferred_locations: dict[str, CompiledRelationLocation] | None = None,
    selected_names: frozenset[str] | None = None,
) -> str | None:
    """Resolve a reference to a qualified relation name for cursor reads."""

    is_selected: bool = selected_names is not None and ref.ref_name in selected_names
    if (
        ref.ref_kind in {SqlReferenceKind.REF, SqlReferenceKind.SEED}
        and deferred_locations is not None
        and ref.ref_name in deferred_locations
        and not is_selected
    ):
        return deferred_locations[ref.ref_name].qualified_name
    if ref.ref_kind == SqlReferenceKind.REF:
        upstream_model: CompiledModel | None = model_map.get(ref.ref_name)
        if upstream_model is not None:
            return upstream_model.destination.qualified_name
        upstream_seed: CompiledSeed | None = seed_map.get(ref.ref_name)
        if upstream_seed is not None:
            return upstream_seed.destination.qualified_name
    elif ref.ref_kind == SqlReferenceKind.SEED:
        seed: CompiledSeed | None = seed_map.get(ref.ref_name)
        if seed is not None:
            return seed.destination.qualified_name
    elif ref.ref_kind == SqlReferenceKind.SOURCE:
        source: CompiledSource | None = source_map.get(ref.ref_name)
        if source is not None:
            entry: SourceEntry = source.source_entry
            return render_source_relation(entry=entry, adapter=adapter)
    return None


def _selected_runtime_producer_names(
    *, project: CompiledProject, selected_keys: frozenset[CompiledObjectKey] | None
) -> frozenset[str]:
    """Return selected warehouse relations produced during this planner invocation."""

    if selected_keys is None:
        return frozenset()
    source_load_names: frozenset[str] = frozenset(
        source.name for source in project.sources if source.source_entry.loader is not None
    )
    names: set[str] = set()
    key: CompiledObjectKey
    for key in selected_keys:
        if key.resource_type in {CompiledResourceType.MODEL, CompiledResourceType.SEED}:
            names.add(key.name)
        elif key.resource_type == CompiledResourceType.SOURCE and key.name in source_load_names:
            names.add(key.name)
    return frozenset(names)


def _resolve_lineage_reference(
    *,
    model: CompiledModel,
    input_name: str,
    model_map: dict[str, CompiledModel],
) -> CompileSqlReference:
    """Resolve one watermark input from transitive upstream lineage."""

    pending: list[CompileSqlReference] = list(model.references)
    visited_models: set[str] = set()
    while pending:
        reference: CompileSqlReference = pending.pop(0)
        if reference.ref_name == input_name:
            return reference
        if reference.ref_kind != SqlReferenceKind.REF or reference.ref_name in visited_models:
            continue
        visited_models.add(reference.ref_name)
        upstream_model: CompiledModel | None = model_map.get(reference.ref_name)
        if upstream_model is not None:
            pending.extend(upstream_model.references)
    raise PlannerInputError(
        f"model '{model.name}': cursor_watermark_inputs references '{input_name}', but it is "
        "not in the model's upstream lineage",
        code="S302",
    )


def _validate_watermark_contract_column(
    *,
    model: CompiledModel,
    ref: CompileSqlReference,
    cursor_column: str,
    model_map: dict[str, CompiledModel],
    source_map: dict[str, CompiledSource],
    seed_map: dict[str, CompiledSeed],
) -> None:
    """Validate reliable watermark column contracts before warehouse inspection."""

    declared_names: tuple[str, ...] = ()
    if ref.ref_kind == SqlReferenceKind.REF:
        upstream_model: CompiledModel | None = model_map.get(ref.ref_name)
        if upstream_model is None:
            return
        if upstream_model.config.values.get("contract") == ContractPolicy.ENFORCED:
            if upstream_model.schema_entry is not None:
                declared_names = tuple(
                    column.name for column in upstream_model.schema_entry.columns
                )
        elif upstream_model.inferred_columns and not upstream_model.fast_lineage_has_star:
            declared_names = tuple(column.name for column in upstream_model.inferred_columns)
        else:
            return
    elif ref.ref_kind == SqlReferenceKind.SOURCE:
        upstream_source: CompiledSource | None = source_map.get(ref.ref_name)
        if (
            upstream_source is None
            or upstream_source.source_entry.contract != ContractPolicy.ENFORCED
        ):
            return
        declared_names = tuple(column.name for column in upstream_source.source_entry.columns)
    elif ref.ref_kind == SqlReferenceKind.SEED:
        upstream_seed: CompiledSeed | None = seed_map.get(ref.ref_name)
        if upstream_seed is None:
            return
        declared_names = tuple(column.name for column in upstream_seed.schema_entry.columns)
    else:
        return
    if cursor_column.lower() in {name.lower() for name in declared_names}:
        return
    declared_display: str = ", ".join(declared_names) or "none"
    raise PlannerInputError(
        f"model '{model.name}': cursor_watermark_inputs references '{ref.ref_name}' column "
        f"'{cursor_column}', but its enforced contract does not expose the column. "
        f"Declared contract columns: {declared_display}",
        code="S302",
    )


def _get_config_str(*, model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None
