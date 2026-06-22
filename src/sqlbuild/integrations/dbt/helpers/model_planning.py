"""dbt model planning helpers for interop execution pruning."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledProject
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.planner.main.selection_staleness import (
    classify_selection_staleness_warnings,
)
from sqlbuild.compiler.planner.models import (
    SelectionStalenessGraph,
    SelectionStalenessNodeKey,
    SelectionStalenessWarning,
)
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
    DbtSupportedResourceType,
)
from sqlbuild.spec.models.source import SourceEntry


def build_dbt_model_planning_result(
    *,
    manifest: DbtManifestIndex,
    candidate_unique_ids: Sequence[str],
    selected_unique_ids: Sequence[str] | None = None,
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
    selected_unique_ids_set: frozenset[str] = frozenset(
        candidate_unique_ids if selected_unique_ids is None else selected_unique_ids
    )
    expected_version_hashes: dict[str, str | None] = build_expected_dbt_model_version_hashes(
        manifest=manifest,
        graph=graph,
    )
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
            full_refresh=full_refresh and unique_id in selected_unique_ids_set,
            expected_version_hash=expected_version_hashes.get(unique_id),
        )
    in_selection_changed_seed_unique_ids: frozenset[str] = (
        changed_seed_unique_ids & selected_unique_ids_set
    )
    stale_out_of_selection_seed_unique_ids: frozenset[str] = (
        changed_seed_unique_ids - selected_unique_ids_set
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
        stale_out_of_selection_warning_messages=_stale_out_of_selection_warning_messages(
            manifest=manifest,
            graph=graph,
            selected_unique_ids=selected_unique_ids_set,
            entries_by_unique_id=entries_by_unique_id,
            changed_seed_unique_ids=changed_seed_unique_ids,
            changed_source_unique_ids=changed_source_unique_ids,
        ),
        source_freshness=source_freshness,
        selected_unique_ids=tuple(sorted(selected_unique_ids_set)),
        changed_seed_unique_ids=tuple(sorted(in_selection_changed_seed_unique_ids)),
        stale_out_of_selection_seed_unique_ids=tuple(
            sorted(stale_out_of_selection_seed_unique_ids)
        ),
    )


def _stale_out_of_selection_warning_messages(
    *,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph | None,
    selected_unique_ids: frozenset[str],
    entries_by_unique_id: dict[str, DbtModelPlanEntry],
    changed_seed_unique_ids: frozenset[str],
    changed_source_unique_ids: frozenset[str],
) -> tuple[str, ...]:
    if graph is None:
        return ()
    neutral_graph: SelectionStalenessGraph = SelectionStalenessGraph(
        upstream_deps=_neutral_upstream_deps(graph=graph, manifest=manifest),
        selected_model_names=frozenset(
            unique_id
            for unique_id in selected_unique_ids
            if unique_id in manifest.models_by_unique_id
        ),
        run_model_names=frozenset(
            entry.unique_id
            for entry in entries_by_unique_id.values()
            if entry.action == DbtModelPlanAction.RUN and entry.unique_id in selected_unique_ids
        ),
        run_seed_names=changed_seed_unique_ids & selected_unique_ids,
        run_source_names=frozenset(),
        changed_model_names=frozenset(
            entry.unique_id
            for entry in entries_by_unique_id.values()
            if _entry_is_own_changed(entry)
        ),
        changed_seed_names=changed_seed_unique_ids,
        changed_source_names=changed_source_unique_ids,
    )
    return tuple(
        _format_stale_warning(warning=warning, manifest=manifest)
        for warning in classify_selection_staleness_warnings(neutral_graph)
    )


def _neutral_upstream_deps(
    *, graph: DbtCombinedGraph, manifest: DbtManifestIndex
) -> dict[SelectionStalenessNodeKey, tuple[SelectionStalenessNodeKey, ...]]:
    return {
        _neutral_key(key=key, manifest=manifest): tuple(
            _neutral_key(key=upstream_key, manifest=manifest) for upstream_key in upstream_keys
        )
        for key, upstream_keys in graph.upstream_deps.items()
        if key.owner == DbtCombinedGraphOwner.DBT
    }


def _neutral_key(
    *, key: DbtCombinedGraphKey, manifest: DbtManifestIndex
) -> SelectionStalenessNodeKey:
    resource_type: str = DbtSupportedResourceType.MODEL
    if key.resource_type == DbtCombinedGraphResourceType.SOURCE:
        resource_type = (
            DbtSupportedResourceType.SEED
            if key.name in manifest.seeds_by_unique_id
            else DbtSupportedResourceType.SOURCE
        )
    return SelectionStalenessNodeKey(resource_type=resource_type, name=key.name)


def _entry_is_own_changed(entry: DbtModelPlanEntry) -> bool:
    return entry.action == DbtModelPlanAction.RUN and entry.reason in {
        DbtModelPlanReason.FIRST_RUN,
        DbtModelPlanReason.RELATION_MISSING,
        DbtModelPlanReason.CHECKSUM_CHANGED,
        DbtModelPlanReason.FULL_REFRESH,
    }


def _entry_version_mismatch(entry: DbtModelPlanEntry) -> bool:
    return (
        entry.previous_version_hash is not None
        and entry.expected_version_hash is not None
        and entry.previous_version_hash != entry.expected_version_hash
    )


def _format_stale_warning(*, warning: SelectionStalenessWarning, manifest: DbtManifestIndex) -> str:
    model_name: str = _display_trigger_name(unique_id=warning.model_name, manifest=manifest)
    trigger_names: tuple[str, ...] = tuple(
        _display_trigger_name(unique_id=trigger_name, manifest=manifest)
        for trigger_name in warning.trigger_names
    )
    changed_seed_names: tuple[str, ...] = tuple(
        _display_trigger_name(unique_id=trigger_name, manifest=manifest)
        for trigger_name in warning.trigger_names
        if trigger_name in manifest.seeds_by_unique_id
    )
    if changed_seed_names:
        return (
            f"selected dbt model '{model_name}' "
            f"is stale: seed(s) {', '.join(changed_seed_names)} changed but were not selected; "
            "rebuild with a closure selector (e.g. +model) to incorporate it"
        )
    return (
        f"selected dbt model '{model_name}' "
        f"is stale: upstream {_format_trigger_names(trigger_names)}; "
        "rebuild with a closure selector (e.g. +model) to incorporate it"
    )


def _display_trigger_name(*, unique_id: str, manifest: DbtManifestIndex) -> str:
    model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
    if model is not None:
        return model.name
    seed: DbtManifestSeed | None = manifest.seeds_by_unique_id.get(unique_id)
    if seed is not None:
        return seed.name
    return unique_id.split(".")[-1]


def _format_trigger_names(names: tuple[str, ...]) -> str:
    return ", ".join(f"{name} changed but will not be rebuilt or is stale" for name in names)


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
    selected_unique_ids: frozenset[str],
    blocked_source_unique_ids: frozenset[str],
    changed_source_unique_ids: frozenset[str],
    changed_seed_unique_ids: frozenset[str],
) -> dict[str, DbtModelPlanEntry]:
    propagated: dict[str, DbtModelPlanEntry] = dict(entries_by_unique_id)
    upstream_by_unique_id: dict[str, frozenset[DbtCombinedGraphKey]] = {
        unique_id: expand_combined_upstream(dbt_model_graph_key(unique_id), graph.upstream_deps)
        for unique_id in entries_by_unique_id
    }
    direct_upstream_by_unique_id: dict[str, tuple[DbtCombinedGraphKey, ...]] = {
        unique_id: graph.upstream_deps.get(dbt_model_graph_key(unique_id), ())
        for unique_id in entries_by_unique_id
    }
    for unique_id, entry in tuple(propagated.items()):
        upstream: frozenset[DbtCombinedGraphKey] = upstream_by_unique_id[unique_id]
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
    changed: bool = True
    while changed:
        changed = False
        for unique_id, entry in tuple(propagated.items()):
            if unique_id not in selected_unique_ids or entry.action != DbtModelPlanAction.CURRENT:
                continue
            direct_upstream: tuple[DbtCombinedGraphKey, ...] = direct_upstream_by_unique_id[
                unique_id
            ]
            upstream_run: bool = any(
                key.owner == DbtCombinedGraphOwner.DBT
                and key.resource_type == DbtCombinedGraphResourceType.MODEL
                and key.name in selected_unique_ids
                and key.name in propagated
                and propagated[key.name].action == DbtModelPlanAction.RUN
                for key in direct_upstream
            )
            selected_upstream_version_mismatch: bool = any(
                key.owner == DbtCombinedGraphOwner.DBT
                and key.resource_type == DbtCombinedGraphResourceType.MODEL
                and key.name in selected_unique_ids
                for key in direct_upstream
            ) and _entry_version_mismatch(entry)
            if upstream_run or selected_upstream_version_mismatch:
                propagated[unique_id] = replace(
                    entry,
                    action=DbtModelPlanAction.RUN,
                    reason=DbtModelPlanReason.UPSTREAM_CHANGED,
                )
                changed = True
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


def build_expected_dbt_model_version_hashes(
    *, manifest: DbtManifestIndex, graph: DbtCombinedGraph | None
) -> dict[str, str | None]:
    hashes: dict[str, str | None] = {}

    def resolve(unique_id: str, visiting: frozenset[str] = frozenset()) -> str | None:
        cached: str | None
        if unique_id in hashes:
            return hashes[unique_id]
        model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
        if model is None:
            hashes[unique_id] = None
            return None
        own_hash: str | None = model.node_checksum
        if own_hash is None:
            hashes[unique_id] = None
            return None
        if graph is None or unique_id in visiting:
            hashes[unique_id] = own_hash
            return own_hash
        upstream_hashes: list[tuple[str, str]] = []
        key: DbtCombinedGraphKey
        for key in graph.upstream_deps.get(dbt_model_graph_key(unique_id), ()):
            if key.owner != DbtCombinedGraphOwner.DBT:
                continue
            upstream_hash: str | None = None
            if key.resource_type == DbtCombinedGraphResourceType.MODEL:
                upstream_hash = resolve(key.name, visiting | {unique_id})
            elif key.resource_type == DbtCombinedGraphResourceType.SOURCE:
                seed: DbtManifestSeed | None = manifest.seeds_by_unique_id.get(key.name)
                upstream_hash = None if seed is None else seed.identity_hash
            if upstream_hash is not None:
                upstream_hashes.append((key.name, upstream_hash))
        if not upstream_hashes:
            hashes[unique_id] = own_hash
            return own_hash
        payload: str = json.dumps(
            {"own": own_hash, "upstream": sorted(upstream_hashes)},
            sort_keys=True,
            separators=(",", ":"),
        )
        cached = hashlib.sha256(payload.encode()).hexdigest()
        hashes[unique_id] = cached
        return cached

    unique_id: str
    for unique_id in manifest.models_by_unique_id:
        resolve(unique_id)
    return hashes


def _plan_model(
    *,
    model: DbtManifestModel,
    fingerprint: Fingerprint | None,
    adapter: BaseAdapter,
    connection: Any,
    full_refresh: bool,
    expected_version_hash: str | None,
) -> DbtModelPlanEntry:
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
    if model.node_checksum is not None and fingerprint.definition_hash != model.node_checksum:
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
