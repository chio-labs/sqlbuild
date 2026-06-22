"""dbt model planning helpers for interop execution pruning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledProject
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.source_freshness.main.planning import (
    build_standard_source_freshness_planning_result,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from sqlbuild.integrations.dbt.helpers.graph import (
    dbt_model_graph_key,
    expand_combined_downstream,
    expand_combined_upstream,
)
from sqlbuild.integrations.dbt.helpers.source_freshness import (
    translate_manifest_sources_to_sqlbuild_sources,
)
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSeed,
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
from sqlbuild.spec.models.source import SourceEntry


def build_dbt_model_planning_result(
    *,
    manifest: DbtManifestIndex,
    candidate_unique_ids: Sequence[str],
    project: CompiledProject,
    graph: DbtCombinedGraph | None = None,
    full_refresh: bool = False,
    adapter: BaseAdapter,
    connection: Any,
) -> DbtModelPlanningResult:
    """Classify dbt model candidates as runnable or current from state and relations."""

    fingerprints: dict[tuple[str, str], Fingerprint] = _read_dbt_fingerprints(
        project=project,
        adapter=adapter,
        connection=connection,
    )
    source_freshness: StandardSourceFreshnessPlanningResult = _source_freshness_result(
        manifest=manifest,
        project=project,
        adapter=adapter,
        connection=connection,
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
        adapter=adapter,
        connection=connection,
    )
    entries_by_unique_id: dict[str, DbtModelPlanEntry] = {}
    unique_id: str
    selected_unique_ids: frozenset[str] = frozenset(candidate_unique_ids)
    expanded_candidate_unique_ids: tuple[str, ...] = _expand_candidate_unique_ids(
        candidate_unique_ids=candidate_unique_ids,
        graph=graph,
    )
    for unique_id in expanded_candidate_unique_ids:
        model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
        if model is None:
            continue
        entries_by_unique_id[unique_id] = _plan_model(
            model=model,
            fingerprint=fingerprints.get((NODE_TYPE_DBT, unique_id)),
            adapter=adapter,
            connection=connection,
            full_refresh=full_refresh and unique_id in selected_unique_ids,
        )
    in_selection_changed_seed_unique_ids: frozenset[str] = (
        changed_seed_unique_ids & selected_unique_ids
    )
    stale_out_of_selection_seed_unique_ids: frozenset[str] = (
        changed_seed_unique_ids - selected_unique_ids
    )
    if graph is not None:
        entries_by_unique_id = _apply_graph_propagation(
            entries_by_unique_id=entries_by_unique_id,
            graph=graph,
            blocked_source_unique_ids=blocked_source_unique_ids,
            changed_source_unique_ids=changed_source_unique_ids,
            changed_seed_unique_ids=in_selection_changed_seed_unique_ids,
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
        source_freshness=source_freshness,
        selected_unique_ids=tuple(sorted(frozenset(candidate_unique_ids))),
        changed_seed_unique_ids=tuple(sorted(in_selection_changed_seed_unique_ids)),
        stale_out_of_selection_seed_unique_ids=tuple(
            sorted(stale_out_of_selection_seed_unique_ids)
        ),
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
            dbt_model_graph_key(unique_id), graph.upstream_deps
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
    adapter: BaseAdapter,
    connection: Any,
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
        if not adapter.relation_exists(
            connection,
            database=seed.database,
            schema=seed.schema,
            name=seed.alias or seed.name,
        ):
            changed.add(seed.unique_id)
    return frozenset(changed)


def _source_freshness_result(
    *,
    manifest: DbtManifestIndex,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
) -> StandardSourceFreshnessPlanningResult:
    sources: tuple[SourceEntry, ...] = translate_manifest_sources_to_sqlbuild_sources(
        manifest=manifest
    )
    if not sources:
        return StandardSourceFreshnessPlanningResult()
    return build_standard_source_freshness_planning_result(
        adapter=adapter,
        connection=connection,
        sources=sources,
        state_database=project.effective_target_database,
        state_schemas=_state_schemas(project),
        observed_at=datetime.now(UTC),
        run_id="dbt-planning",
        render_qualified_name=adapter.render_qualified_name,
    )


def _apply_graph_propagation(
    *,
    entries_by_unique_id: dict[str, DbtModelPlanEntry],
    graph: DbtCombinedGraph,
    blocked_source_unique_ids: frozenset[str],
    changed_source_unique_ids: frozenset[str],
    changed_seed_unique_ids: frozenset[str],
) -> dict[str, DbtModelPlanEntry]:
    propagated: dict[str, DbtModelPlanEntry] = dict(entries_by_unique_id)
    for unique_id, entry in entries_by_unique_id.items():
        upstream: frozenset[DbtCombinedGraphKey] = expand_combined_upstream(
            dbt_model_graph_key(unique_id), graph.upstream_deps
        )
        blocked_sources: tuple[str, ...] = tuple(
            sorted(
                key.name
                for key in upstream
                if key.owner == DbtCombinedGraphOwner.DBT
                and key.resource_type == DbtCombinedGraphResourceType.SOURCE
                and key.name in blocked_source_unique_ids
            )
        )
        if blocked_sources:
            propagated[unique_id] = replace(
                entry,
                action=DbtModelPlanAction.BLOCKED,
                reason=DbtModelPlanReason.SOURCE_FRESHNESS_ERROR,
                blocked_source_unique_ids=blocked_sources,
            )
            continue
        changed_sources: tuple[str, ...] = tuple(
            sorted(
                key.name
                for key in upstream
                if key.owner == DbtCombinedGraphOwner.DBT
                and key.resource_type == DbtCombinedGraphResourceType.SOURCE
                and key.name in changed_source_unique_ids
            )
        )
        if changed_sources and entry.action == DbtModelPlanAction.CURRENT:
            propagated[unique_id] = replace(
                entry,
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.SOURCE_FRESHNESS_CHANGED,
            )
            continue
        changed_seeds: bool = any(
            key.owner == DbtCombinedGraphOwner.DBT
            and key.resource_type == DbtCombinedGraphResourceType.SOURCE
            and key.name in changed_seed_unique_ids
            for key in upstream
        )
        if changed_seeds and entry.action == DbtModelPlanAction.CURRENT:
            propagated[unique_id] = replace(
                entry,
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.UPSTREAM_CHANGED,
            )
            continue
        upstream_run: bool = any(
            key.owner == DbtCombinedGraphOwner.DBT
            and key.resource_type == DbtCombinedGraphResourceType.MODEL
            and key.name in entries_by_unique_id
            and entries_by_unique_id[key.name].action == DbtModelPlanAction.RUN
            for key in upstream
        )
        if upstream_run and entry.action == DbtModelPlanAction.CURRENT:
            propagated[unique_id] = replace(
                entry,
                action=DbtModelPlanAction.RUN,
                reason=DbtModelPlanReason.UPSTREAM_CHANGED,
            )
    return propagated


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
            dbt_model_graph_key(unique_id), graph.downstream_deps
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
    *, project: CompiledProject, adapter: BaseAdapter, connection: Any
) -> dict[tuple[str, str], Fingerprint]:
    schema: str | None = project.effective_target_schema
    if schema is None:
        return {}
    fingerprint_set: FingerprintSet = read_latest_fingerprints(
        connection=connection,
        execute=adapter.execute,
        relation_exists=adapter.relation_exists,
        database=project.effective_target_database,
        schema=schema,
        render_qualified_name=adapter.render_qualified_name,
        render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
    )
    return dict(fingerprint_set.fingerprints_by_identity or {})


def _plan_model(
    *,
    model: DbtManifestModel,
    fingerprint: Fingerprint | None,
    adapter: BaseAdapter,
    connection: Any,
    full_refresh: bool,
) -> DbtModelPlanEntry:
    expected_version_hash: str | None = model.node_checksum
    if full_refresh:
        return _entry(
            model=model,
            action=DbtModelPlanAction.RUN,
            reason=DbtModelPlanReason.FULL_REFRESH,
            fingerprint=fingerprint,
            expected_version_hash=expected_version_hash,
        )
    relation_exists: bool = adapter.relation_exists(
        connection,
        database=model.database,
        schema=model.schema,
        name=model.alias or model.name,
    )
    if fingerprint is None:
        return _entry(
            model=model,
            action=DbtModelPlanAction.RUN,
            reason=DbtModelPlanReason.FIRST_RUN,
            expected_version_hash=expected_version_hash,
        )
    if not relation_exists:
        return _entry(
            model=model,
            action=DbtModelPlanAction.RUN,
            reason=DbtModelPlanReason.RELATION_MISSING,
            fingerprint=fingerprint,
            expected_version_hash=expected_version_hash,
        )
    if expected_version_hash is not None and fingerprint.version_hash != expected_version_hash:
        return _entry(
            model=model,
            action=DbtModelPlanAction.RUN,
            reason=DbtModelPlanReason.CHECKSUM_CHANGED,
            fingerprint=fingerprint,
            expected_version_hash=expected_version_hash,
        )
    return _entry(
        model=model,
        action=DbtModelPlanAction.CURRENT,
        reason=DbtModelPlanReason.NO_CHANGE,
        fingerprint=fingerprint,
        expected_version_hash=expected_version_hash,
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
