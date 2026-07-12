"""dbt model planning helpers for interop execution pruning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledProject
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME, NODE_TYPE_DBT
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.planner.main.planning.graph_changes_only import (
    build_graph_changes_only_propagation,
)
from sqlbuild.compiler.planner.main.planning.graph_identity import (
    build_expected_graph_identity_hashes,
)
from sqlbuild.compiler.planner.main.planning.local_node_planning import classify_local_node_plan
from sqlbuild.compiler.planner.main.planning.selection_staleness import (
    classify_selection_staleness_warnings,
)
from sqlbuild.compiler.planner.main.planning.stale_warning_message import (
    format_stale_upstream_warning_message,
)
from sqlbuild.compiler.planner.models import (
    GraphChangesOnlyPropagationInput,
    GraphChangesOnlyPropagationResult,
    GraphIdentityNode,
    GraphNodeKey,
    SelectionStalenessGraph,
)
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.compiler.source_freshness.main.planning import (
    build_standard_source_freshness_planning_result,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from sqlbuild.integrations.dbt.helpers.graph.core import (
    dbt_model_graph_key,
    expand_combined_downstream,
    expand_combined_upstream,
)
from sqlbuild.integrations.dbt.helpers.planning.graph_projection import (
    dbt_graph_node_key,
    dbt_graph_node_upstream_deps,
    dbt_selection_staleness_upstream_deps,
)
from sqlbuild.integrations.dbt.helpers.planning.model_identity import (
    build_dbt_graph_identity_nodes,
    compose_dbt_graph_version_hash,
    dbt_graph_identity_execution_order,
)
from sqlbuild.integrations.dbt.helpers.runtime.node_source_watermarks import (
    build_dbt_node_source_watermark_staleness_warning,
)
from sqlbuild.integrations.dbt.helpers.runtime.source_freshness import (
    translate_manifest_sources_to_sqlbuild_sources,
)
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSeed,
    DbtManifestSource,
)
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtModelPlanEntry,
    DbtModelPlanningResult,
)
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtModelPlanAction,
    DbtModelPlanReason,
)
from sqlbuild.shared.models import LocalNodePlanInput, LocalNodePlanOutcome, RelationLookup
from sqlbuild.shared.types import LocalNodePlanAction, LocalNodePlanReason
from sqlbuild.spec.models.source import SourceEntry


def build_dbt_model_planning_result(
    *,
    manifest: DbtManifestIndex,
    candidate_unique_ids: Sequence[str],
    selected_unique_ids: Sequence[str] | None = None,
    project: CompiledProject,
    graph: DbtCombinedGraph | None = None,
    full_refresh: bool = False,
    force: bool = False,
    adapter: BaseAdapter,
    connection: Any,
) -> DbtModelPlanningResult:
    """Classify dbt model candidates as runnable or current from state and relations."""

    expanded_candidate_unique_ids: tuple[str, ...] = _expand_candidate_unique_ids(
        candidate_unique_ids=candidate_unique_ids,
        graph=graph,
    )
    candidate_models: tuple[DbtManifestModel, ...] = tuple(
        model
        for unique_id in expanded_candidate_unique_ids
        if (model := manifest.models_by_unique_id.get(unique_id)) is not None
    )
    relation_lookup: RelationLookup = _build_relation_lookup(
        adapter=adapter,
        connection=connection,
        models=candidate_models,
        seeds=tuple(manifest.seeds_by_unique_id.values()),
        state_database=project.effective_target_database,
        state_schemas=_state_schemas(project),
    )
    fingerprints: dict[tuple[str, str], Fingerprint] = _read_dbt_fingerprints(
        project=project,
        adapter=adapter,
        connection=connection,
        relation_lookup=relation_lookup,
    )
    source_freshness: StandardSourceFreshnessPlanningResult = _source_freshness_result(
        manifest=manifest,
        candidate_unique_ids=expanded_candidate_unique_ids,
        project=project,
        graph=graph,
        adapter=adapter,
        connection=connection,
        relation_lookup=relation_lookup,
    )
    blocked_source_unique_ids: frozenset[str] = frozenset(
        identity.source_name
        for identity, status in source_freshness.age_statuses.items()
        if status == SourceFreshnessAgeStatus.ERROR
    )
    changed_source_unique_ids: frozenset[str] = frozenset(
        identity.source_name for identity in source_freshness.changed_identities
    )
    changed_seed_unique_ids: frozenset[str] = _changed_seed_unique_ids(
        manifest=manifest,
        fingerprints=fingerprints,
        full_refresh=full_refresh,
        relation_lookup=relation_lookup,
    )
    entries_by_unique_id: dict[str, DbtModelPlanEntry] = {}
    unique_id: str
    selected_unique_ids_set: frozenset[str] = frozenset(
        candidate_unique_ids if selected_unique_ids is None else selected_unique_ids
    )
    expected_version_hashes: dict[str, str | None] = build_expected_dbt_model_version_hashes(
        manifest=manifest,
        graph=graph,
    )
    for unique_id in expanded_candidate_unique_ids:
        model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
        if model is None:
            continue
        entries_by_unique_id[unique_id] = _plan_model(
            model=model,
            fingerprint=fingerprints.get((NODE_TYPE_DBT, unique_id)),
            relation_exists=_model_relation_exists(model=model, relation_lookup=relation_lookup),
            full_refresh=full_refresh and unique_id in selected_unique_ids_set,
            expected_version_hash=expected_version_hashes.get(unique_id),
        )
    if force:
        entries_by_unique_id = _force_selected_current_entries(
            entries_by_unique_id=entries_by_unique_id,
            selected_unique_ids=selected_unique_ids_set,
        )
    in_selection_changed_seed_unique_ids: frozenset[str] = (
        changed_seed_unique_ids & selected_unique_ids_set
    )
    if graph is not None:
        entries_by_unique_id = _apply_graph_propagation(
            entries_by_unique_id=entries_by_unique_id,
            graph=graph,
            selected_unique_ids=selected_unique_ids_set,
            blocked_source_unique_ids=blocked_source_unique_ids,
            changed_source_unique_ids=changed_source_unique_ids,
            changed_seed_unique_ids=in_selection_changed_seed_unique_ids,
        )
    stale_out_of_selection_warning_messages: tuple[str, ...] = ()
    if graph is not None:
        stale_out_of_selection_warning_messages = (
            *stale_out_of_selection_warning_messages,
            *_build_stale_out_of_selection_model_warning_messages(
                manifest=manifest,
                graph=graph,
                entries_by_unique_id=entries_by_unique_id,
                selected_unique_ids=selected_unique_ids_set,
                changed_seed_unique_ids=changed_seed_unique_ids,
                changed_source_unique_ids=changed_source_unique_ids,
            ),
        )
    if graph is not None and (
        node_source_watermark_warning := build_dbt_node_source_watermark_staleness_warning(
            manifest=manifest,
            graph=graph,
            selected_unique_ids=tuple(sorted(selected_unique_ids_set)),
            source_records=source_freshness.observed_records,
            adapter=adapter,
            connection=connection,
            state_database=project.effective_target_database,
            state_schema=project.effective_target_schema,
        )
    ):
        stale_out_of_selection_warning_messages = (
            *stale_out_of_selection_warning_messages,
            node_source_watermark_warning,
        )
    return DbtModelPlanningResult(
        entries=tuple(
            entries_by_unique_id[unique_id] for unique_id in sorted(entries_by_unique_id)
        ),
        stale_sqlbuild_model_names=_downstream_sqlbuild_model_names(
            graph=graph,
            dbt_unique_ids=tuple(
                entry.unique_id
                for entry in entries_by_unique_id.values()
                if entry.action == DbtModelPlanAction.RUN
            ),
        ),
        blocked_sqlbuild_model_names=_blocked_sqlbuild_model_names(
            graph=graph,
            blocked_dbt_unique_ids=tuple(
                entry.unique_id
                for entry in entries_by_unique_id.values()
                if entry.action == DbtModelPlanAction.BLOCKED
            ),
        ),
        stale_out_of_selection_warning_messages=stale_out_of_selection_warning_messages,
        source_freshness=source_freshness,
        selected_unique_ids=tuple(sorted(selected_unique_ids_set)),
        changed_seed_unique_ids=tuple(sorted(in_selection_changed_seed_unique_ids)),
    )


def _force_selected_current_entries(
    *,
    entries_by_unique_id: dict[str, DbtModelPlanEntry],
    selected_unique_ids: frozenset[str],
) -> dict[str, DbtModelPlanEntry]:
    forced: dict[str, DbtModelPlanEntry] = dict(entries_by_unique_id)
    unique_id: str
    for unique_id in selected_unique_ids:
        entry: DbtModelPlanEntry | None = forced.get(unique_id)
        if entry is None or entry.action != DbtModelPlanAction.CURRENT:
            continue
        forced[unique_id] = replace(
            entry,
            action=DbtModelPlanAction.RUN,
            reason=DbtModelPlanReason.FORCED,
        )
    return forced


def _entry_version_mismatch(entry: DbtModelPlanEntry) -> bool:
    return (
        entry.previous_version_hash is not None
        and entry.expected_version_hash is not None
        and entry.previous_version_hash != entry.expected_version_hash
    )


def build_downstream_sqlbuild_model_names(
    *, graph: DbtCombinedGraph | None, dbt_unique_ids: tuple[str, ...]
) -> tuple[str, ...]:
    """Return SQLBuild model names downstream of dbt model unique IDs."""

    return _downstream_sqlbuild_model_names(graph=graph, dbt_unique_ids=dbt_unique_ids)


def _expand_candidate_unique_ids(
    *, candidate_unique_ids: Sequence[str], graph: DbtCombinedGraph | None
) -> tuple[str, ...]:
    if graph is None:
        return tuple(sorted(frozenset(candidate_unique_ids)))
    unique_ids: set[str] = set(candidate_unique_ids)
    unique_id: str
    for unique_id in candidate_unique_ids:
        upstream: frozenset[DbtCombinedGraphKey] = expand_combined_upstream(
            key=dbt_model_graph_key(unique_id), upstream=graph.upstream_deps
        )
        key: DbtCombinedGraphKey
        for key in upstream:
            if (
                key.owner == DbtCombinedGraphOwner.DBT
                and key.resource_type == DbtCombinedGraphResourceType.MODEL
            ):
                unique_ids.add(key.name)
    return tuple(sorted(unique_ids))


def _changed_seed_unique_ids(
    *,
    manifest: DbtManifestIndex,
    fingerprints: dict[tuple[str, str], Fingerprint],
    full_refresh: bool,
    relation_lookup: RelationLookup,
) -> frozenset[str]:
    changed: set[str] = set()
    seed: DbtManifestSeed
    for seed in manifest.seeds_by_unique_id.values():
        if full_refresh:
            changed.add(seed.unique_id)
            continue
        fingerprint: Fingerprint | None = fingerprints.get((NODE_TYPE_DBT, seed.unique_id))
        if fingerprint is None or fingerprint.version_hash != seed.identity_hash:
            changed.add(seed.unique_id)
            continue
        if not _seed_relation_exists(seed=seed, relation_lookup=relation_lookup):
            changed.add(seed.unique_id)
    return frozenset(changed)


def _source_freshness_result(
    *,
    manifest: DbtManifestIndex,
    candidate_unique_ids: Sequence[str],
    project: CompiledProject,
    graph: DbtCombinedGraph | None,
    adapter: BaseAdapter,
    connection: Any,
    relation_lookup: RelationLookup,
) -> StandardSourceFreshnessPlanningResult:
    sources_by_unique_id: dict[str, DbtManifestSource] = _freshness_sources_by_unique_id(
        manifest=manifest,
        candidate_unique_ids=candidate_unique_ids,
        graph=graph,
    )
    scoped_manifest: DbtManifestIndex = replace(
        manifest,
        sources_by_unique_id=sources_by_unique_id,
    )
    sources: tuple[SourceEntry, ...] = translate_manifest_sources_to_sqlbuild_sources(
        manifest=scoped_manifest
    )
    if not sources:
        return StandardSourceFreshnessPlanningResult()
    state_schemas: tuple[str, ...] = _state_schemas(project)
    state_table_exists_by_schema: dict[str, bool] = {
        state_schema: relation_lookup.exists(
            database=project.effective_target_database,
            schema=state_schema,
            name=SOURCE_FRESHNESS_TABLE_NAME,
        )
        for state_schema in state_schemas
    }
    return build_standard_source_freshness_planning_result(
        adapter=adapter,
        connection=connection,
        sources=sources,
        state_database=project.effective_target_database,
        state_schemas=state_schemas,
        observed_at=datetime.now(UTC),
        run_id="dbt-planning",
        render_qualified_name=adapter.render_qualified_name,
        state_table_exists_by_schema=state_table_exists_by_schema,
    )


def _freshness_sources_by_unique_id(
    *,
    manifest: DbtManifestIndex,
    candidate_unique_ids: Sequence[str],
    graph: DbtCombinedGraph | None,
) -> dict[str, DbtManifestSource]:
    return manifest.sources_by_unique_id


def _apply_graph_propagation(
    *,
    entries_by_unique_id: dict[str, DbtModelPlanEntry],
    graph: DbtCombinedGraph,
    selected_unique_ids: frozenset[str],
    blocked_source_unique_ids: frozenset[str],
    changed_source_unique_ids: frozenset[str],
    changed_seed_unique_ids: frozenset[str],
) -> dict[str, DbtModelPlanEntry]:
    propagated: dict[str, DbtModelPlanEntry] = dict(entries_by_unique_id)
    propagation: GraphChangesOnlyPropagationResult = build_graph_changes_only_propagation(
        request=GraphChangesOnlyPropagationInput(
            upstream_deps=dbt_graph_node_upstream_deps(graph=graph),
            model_keys=frozenset(
                dbt_graph_node_key(unique_id) for unique_id in entries_by_unique_id
            ),
            selected_model_keys=frozenset(
                dbt_graph_node_key(unique_id) for unique_id in selected_unique_ids
            ),
            current_model_keys=frozenset(
                dbt_graph_node_key(unique_id)
                for unique_id, entry in entries_by_unique_id.items()
                if entry.action == DbtModelPlanAction.CURRENT
            ),
            run_model_keys=frozenset(
                dbt_graph_node_key(unique_id)
                for unique_id, entry in entries_by_unique_id.items()
                if entry.action == DbtModelPlanAction.RUN
            ),
            version_mismatch_model_keys=frozenset(
                dbt_graph_node_key(unique_id)
                for unique_id, entry in entries_by_unique_id.items()
                if _entry_version_mismatch(entry)
            ),
            changed_seed_keys=frozenset(
                dbt_graph_node_key(unique_id) for unique_id in changed_seed_unique_ids
            ),
            changed_source_keys=frozenset(
                dbt_graph_node_key(unique_id) for unique_id in changed_source_unique_ids
            ),
            blocked_source_keys=frozenset(
                dbt_graph_node_key(unique_id) for unique_id in blocked_source_unique_ids
            ),
        )
    )
    unique_id: str
    for unique_id, entry in tuple(propagated.items()):
        key: GraphNodeKey = dbt_graph_node_key(unique_id)
        if key in propagation.blocked_model_keys:
            blocked_sources: tuple[str, ...] = tuple(
                source_key.node_name
                for source_key in propagation.blocked_source_keys_by_model_key.get(key, ())
            )
            propagated[unique_id] = replace(
                entry,
                action=DbtModelPlanAction.BLOCKED,
                reason=DbtModelPlanReason.SOURCE_FRESHNESS_ERROR,
                blocked_source_unique_ids=blocked_sources,
            )
            continue
        if key in propagation.source_changed_model_keys:
            propagated[unique_id] = replace(
                entry,
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.SOURCE_FRESHNESS_CHANGED,
            )
            continue
        if key in propagation.seed_changed_model_keys:
            propagated[unique_id] = replace(
                entry,
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.UPSTREAM_CHANGED,
            )
            continue
        if key in propagation.upstream_changed_model_keys:
            propagated[unique_id] = replace(
                entry,
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.UPSTREAM_CHANGED,
            )
    return propagated


def _build_stale_out_of_selection_model_warning_messages(
    *,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    entries_by_unique_id: dict[str, DbtModelPlanEntry],
    selected_unique_ids: frozenset[str],
    changed_seed_unique_ids: frozenset[str],
    changed_source_unique_ids: frozenset[str],
) -> tuple[str, ...]:
    neutral_graph: SelectionStalenessGraph = SelectionStalenessGraph(
        upstream_deps=dbt_selection_staleness_upstream_deps(manifest=manifest, graph=graph),
        selected_model_names=frozenset(
            manifest.models_by_unique_id[unique_id].name
            for unique_id in selected_unique_ids
            if unique_id in manifest.models_by_unique_id
        ),
        run_model_names=frozenset(
            entry.name
            for unique_id, entry in entries_by_unique_id.items()
            if unique_id in selected_unique_ids and entry.action == DbtModelPlanAction.RUN
        ),
        run_seed_names=frozenset(
            manifest.seeds_by_unique_id[unique_id].name
            for unique_id in changed_seed_unique_ids & selected_unique_ids
            if unique_id in manifest.seeds_by_unique_id
        ),
        run_source_names=frozenset(
            manifest.sources_by_unique_id[unique_id].name
            for unique_id in changed_source_unique_ids & selected_unique_ids
            if unique_id in manifest.sources_by_unique_id
        ),
        changed_model_names=frozenset(
            entry.name for entry in entries_by_unique_id.values() if _entry_has_own_change(entry)
        ),
        changed_seed_names=frozenset(
            manifest.seeds_by_unique_id[unique_id].name
            for unique_id in changed_seed_unique_ids
            if unique_id in manifest.seeds_by_unique_id
        ),
        changed_source_names=frozenset(
            manifest.sources_by_unique_id[unique_id].name
            for unique_id in changed_source_unique_ids
            if unique_id in manifest.sources_by_unique_id
        ),
    )
    return tuple(
        format_stale_upstream_warning_message(
            model_label="selected dbt model",
            model_name=warning.model_name,
            trigger_label="upstream(s)",
            trigger_names=warning.trigger_names,
        )
        for warning in classify_selection_staleness_warnings(neutral_graph)
    )


def _entry_has_own_change(entry: DbtModelPlanEntry) -> bool:
    return entry.reason in {
        DbtModelPlanReason.FIRST_RUN,
        DbtModelPlanReason.FULL_REFRESH,
        DbtModelPlanReason.RELATION_MISSING,
        DbtModelPlanReason.CHECKSUM_CHANGED,
    }


def _blocked_sqlbuild_model_names(
    *, graph: DbtCombinedGraph | None, blocked_dbt_unique_ids: tuple[str, ...]
) -> tuple[str, ...]:
    return _downstream_sqlbuild_model_names(graph=graph, dbt_unique_ids=blocked_dbt_unique_ids)


def _downstream_sqlbuild_model_names(
    *, graph: DbtCombinedGraph | None, dbt_unique_ids: tuple[str, ...]
) -> tuple[str, ...]:
    if graph is None or not dbt_unique_ids:
        return ()
    names: set[str] = set()
    unique_id: str
    for unique_id in dbt_unique_ids:
        downstream: frozenset[DbtCombinedGraphKey] = expand_combined_downstream(
            key=dbt_model_graph_key(unique_id), downstream=graph.downstream_deps
        )
        key: DbtCombinedGraphKey
        for key in downstream:
            if (
                key.owner == DbtCombinedGraphOwner.SQLBUILD
                and key.resource_type == DbtCombinedGraphResourceType.MODEL
            ):
                names.add(key.name)
    return tuple(sorted(names))


def _state_schemas(project: CompiledProject) -> tuple[str, ...]:
    schemas: set[str] = set()
    model: CompiledModel
    for model in project.models:
        if model.destination.schema is not None:
            schemas.add(model.destination.schema)
    if project.effective_target_schema is not None:
        schemas.add(project.effective_target_schema)
    return tuple(sorted(schemas))


def _read_dbt_fingerprints(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    relation_lookup: RelationLookup,
) -> dict[tuple[str, str], Fingerprint]:
    schema: str | None = project.effective_target_schema
    if schema is None:
        return {}
    table_exists: bool = relation_lookup.exists(
        database=project.effective_target_database,
        schema=schema,
        name=FINGERPRINT_TABLE_NAME,
    )
    fingerprint_set: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=adapter.execute,
        table_exists=table_exists,
        database=project.effective_target_database,
        schema=schema,
        render_qualified_name=adapter.render_qualified_name,
        render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
    )
    return dict(fingerprint_set.fingerprints_by_identity or {})


def build_expected_dbt_model_version_hashes(
    *, manifest: DbtManifestIndex, graph: DbtCombinedGraph | None
) -> dict[str, str | None]:
    nodes: dict[GraphNodeKey, GraphIdentityNode] = build_dbt_graph_identity_nodes(
        manifest=manifest,
        graph=graph,
    )
    execution_order: tuple[GraphNodeKey, ...] = dbt_graph_identity_execution_order(
        manifest=manifest
    )
    hashes: dict[GraphNodeKey, str | None] = build_expected_graph_identity_hashes(
        nodes=nodes,
        execution_order=execution_order,
        compose_identity=compose_dbt_graph_version_hash,
    )
    return {
        unique_id: hashes.get(dbt_graph_node_key(unique_id))
        for unique_id in manifest.models_by_unique_id
    }


def _plan_model(
    *,
    model: DbtManifestModel,
    fingerprint: Fingerprint | None,
    relation_exists: bool,
    full_refresh: bool,
    expected_version_hash: str | None,
) -> DbtModelPlanEntry:
    outcome: LocalNodePlanOutcome = classify_local_node_plan(
        LocalNodePlanInput(
            fingerprint_exists=fingerprint is not None,
            relation_exists=relation_exists,
            full_refresh=full_refresh,
            local_hash=model.node_checksum,
            previous_hash=fingerprint.definition_hash if fingerprint is not None else None,
        )
    )
    return _entry(
        model=model,
        action=_dbt_model_plan_action(outcome.action),
        reason=_dbt_model_plan_reason(outcome.reason),
        fingerprint=fingerprint,
        expected_version_hash=expected_version_hash,
    )


def _dbt_model_plan_action(action: LocalNodePlanAction) -> DbtModelPlanAction:
    if action == LocalNodePlanAction.RUN:
        return DbtModelPlanAction.RUN
    return DbtModelPlanAction.CURRENT


def _dbt_model_plan_reason(reason: LocalNodePlanReason) -> DbtModelPlanReason:
    if reason == LocalNodePlanReason.FIRST_RUN:
        return DbtModelPlanReason.FIRST_RUN
    if reason == LocalNodePlanReason.FULL_REFRESH:
        return DbtModelPlanReason.FULL_REFRESH
    if reason == LocalNodePlanReason.RELATION_MISSING:
        return DbtModelPlanReason.RELATION_MISSING
    if reason == LocalNodePlanReason.LOCAL_CHANGED:
        return DbtModelPlanReason.CHECKSUM_CHANGED
    return DbtModelPlanReason.NO_CHANGE


def _build_relation_lookup(
    *,
    adapter: BaseAdapter,
    connection: Any,
    models: tuple[DbtManifestModel, ...],
    seeds: tuple[DbtManifestSeed, ...],
    state_database: str | None,
    state_schemas: tuple[str, ...],
) -> RelationLookup:
    state_location_items: list[tuple[str | None, str | None, str]] = []
    for state_schema in state_schemas:
        for state_table_name in (FINGERPRINT_TABLE_NAME, SOURCE_FRESHNESS_TABLE_NAME):
            state_location_items.append((state_database, state_schema, state_table_name))
    state_locations: tuple[tuple[str | None, str | None, str], ...] = tuple(state_location_items)
    locations: tuple[tuple[str | None, str | None, str], ...] = (
        *((model.database, model.schema, model.alias or model.name) for model in models),
        *((seed.database, seed.schema, seed.alias or seed.name) for seed in seeds),
        *state_locations,
    )
    return build_relation_lookup(adapter=adapter, connection=connection, locations=locations)


def _model_relation_exists(*, model: DbtManifestModel, relation_lookup: RelationLookup) -> bool:
    return relation_lookup.exists(
        database=model.database,
        schema=model.schema,
        name=model.alias or model.name,
    )


def _seed_relation_exists(*, seed: DbtManifestSeed, relation_lookup: RelationLookup) -> bool:
    return relation_lookup.exists(
        database=seed.database,
        schema=seed.schema,
        name=seed.alias or seed.name,
    )


def _entry(
    *,
    model: DbtManifestModel,
    action: DbtModelPlanAction,
    reason: DbtModelPlanReason,
    fingerprint: Fingerprint | None = None,
    expected_version_hash: str | None = None,
) -> DbtModelPlanEntry:
    return DbtModelPlanEntry(
        unique_id=model.unique_id,
        package_name=model.package_name,
        name=model.name,
        action=action,
        reason=reason,
        relation_name=model.relation_name,
        fqn=model.fqn,
        fingerprint_query_sql=model.query_sql,
        previous_query_sql=fingerprint.definition if fingerprint is not None else None,
        previous_version_hash=fingerprint.version_hash if fingerprint is not None else None,
        previous_metadata_json=fingerprint.metadata_json if fingerprint is not None else None,
        expected_version_hash=expected_version_hash,
    )
