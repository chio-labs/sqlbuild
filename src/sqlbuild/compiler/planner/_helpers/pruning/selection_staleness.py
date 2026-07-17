"""Selection-aware stale warning helpers for standard planning."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.pruning.selection_classifier import (
    classify_selection_staleness_warnings,
    format_stale_upstream_warning_message,
)
from sqlbuild.compiler.planner.main.changes._model_changes import detect_model_changes
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    PlannerChangeResults,
    PlannerScope,
    PlanWarning,
    SelectionStalenessGraph,
    SelectionStalenessNodeKey,
    SelectionStalenessWarning,
    StandardModelVersionIdentities,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import ChangeKind, WarningSeverity
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult


def build_stale_out_of_selection_warnings(
    *,
    original_scope: PlannerScope,
    execution_scope: PlannerScope,
    changes: PlannerChangeResults,
    snapshot: WarehouseSnapshot,
    version_identities: StandardModelVersionIdentities,
    source_freshness: StandardSourceFreshnessPlanningResult | None,
    reuse_satisfied_model_names: frozenset[str] = frozenset(),
    include_sources: bool = True,
) -> tuple[PlanWarning, ...]:
    """Warn for selected models stale through changed upstreams outside the run set."""

    run_model_names: frozenset[str] = reuse_satisfied_model_names | frozenset(
        key.name
        for key in execution_scope.selected_keys
        if key.resource_type == CompiledResourceType.MODEL
    )
    run_seed_names: frozenset[str] = frozenset(
        key.name
        for key in execution_scope.selected_keys
        if key.resource_type == CompiledResourceType.SEED
    )
    run_source_names: frozenset[str] = frozenset(
        key.name
        for key in execution_scope.selected_keys
        if key.resource_type == CompiledResourceType.SOURCE
    )
    neutral_graph: SelectionStalenessGraph = SelectionStalenessGraph(
        upstream_deps=_neutral_upstream_deps(original_scope.upstream_deps),
        selected_model_names=frozenset(
            key.name
            for key in original_scope.selected_keys
            if key.resource_type == CompiledResourceType.MODEL
        ),
        run_model_names=run_model_names,
        run_seed_names=run_seed_names,
        run_source_names=run_source_names,
        changed_model_names=_changed_model_names(
            original_scope=original_scope,
            changes=changes,
            snapshot=snapshot,
            version_identities=version_identities,
        )
        - reuse_satisfied_model_names,
        changed_seed_names=_changed_seed_names(
            snapshot=snapshot,
            version_identities=version_identities,
        ),
        changed_source_names=(
            _changed_source_names(source_freshness) if include_sources else frozenset()
        ),
    )
    warnings: list[PlanWarning] = []
    warning: SelectionStalenessWarning
    for warning in classify_selection_staleness_warnings(neutral_graph):
        warnings.append(
            PlanWarning(
                model_name=warning.model_name,
                severity=WarningSeverity.WARNING,
                message=format_stale_upstream_warning_message(
                    model_label="selected model",
                    model_name=warning.model_name,
                    trigger_label="upstream(s)",
                    trigger_names=warning.trigger_names,
                ),
            )
        )
    return tuple(warnings)


def _neutral_upstream_deps(
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[SelectionStalenessNodeKey, tuple[SelectionStalenessNodeKey, ...]]:
    neutral_deps: dict[SelectionStalenessNodeKey, tuple[SelectionStalenessNodeKey, ...]] = {}
    for key, upstream_keys in upstream_deps.items():
        neutral_upstreams: list[SelectionStalenessNodeKey] = []
        for upstream_key in upstream_keys:
            neutral_upstreams.append(_neutral_key(upstream_key))
        neutral_deps[_neutral_key(key)] = tuple(neutral_upstreams)
    return neutral_deps


def _neutral_key(key: CompiledObjectKey) -> SelectionStalenessNodeKey:
    return SelectionStalenessNodeKey(
        resource_type=_neutral_resource_type(key.resource_type),
        name=key.name,
    )


def _neutral_resource_type(resource_type: str) -> str:
    if resource_type == CompiledResourceType.MODEL:
        return "model"
    if resource_type == CompiledResourceType.SEED:
        return "seed"
    if resource_type == CompiledResourceType.SOURCE:
        return "source"
    return str(resource_type)


def _changed_model_names(
    *,
    original_scope: PlannerScope,
    changes: PlannerChangeResults,
    snapshot: WarehouseSnapshot,
    version_identities: StandardModelVersionIdentities,
) -> frozenset[str]:
    changed: set[str] = {
        model_name
        for model_name, change in changes.models.items()
        if change.change_kind
        in {
            ChangeKind.FIRST_RUN,
            ChangeKind.QUERY_CHANGED,
            ChangeKind.CONFIG_CHANGED,
            ChangeKind.SCHEMA_CHANGED,
        }
    }
    changed.update(
        model_name
        for model_name in original_scope.models_by_name
        if _model_own_identity_changed(
            model_name=model_name,
            original_scope=original_scope,
            changes=changes,
            snapshot=snapshot,
            version_identities=version_identities,
        )
    )
    return frozenset(changed)


def _changed_seed_names(
    *,
    snapshot: WarehouseSnapshot,
    version_identities: StandardModelVersionIdentities,
) -> frozenset[str]:
    return frozenset(
        seed_name
        for seed_name in version_identities.seed_version_hashes
        if _seed_identity_changed(
            seed_name=seed_name,
            snapshot=snapshot,
            version_identities=version_identities,
        )
    )


def _changed_source_names(
    source_freshness: StandardSourceFreshnessPlanningResult | None,
) -> frozenset[str]:
    if source_freshness is None:
        return frozenset()
    return frozenset(identity.source_name for identity in source_freshness.changed_identities)


def _model_own_identity_changed(
    *,
    model_name: str,
    original_scope: PlannerScope,
    changes: PlannerChangeResults,
    snapshot: WarehouseSnapshot,
    version_identities: StandardModelVersionIdentities,
) -> bool:
    selected_change: ChangeDetectionResult | None = changes.models.get(model_name)
    if selected_change is not None:
        if selected_change.change_kind in {
            ChangeKind.FIRST_RUN,
            ChangeKind.QUERY_CHANGED,
            ChangeKind.CONFIG_CHANGED,
            ChangeKind.SCHEMA_CHANGED,
        }:
            return True
    model: CompiledModel | None = original_scope.models_by_name.get(model_name)
    if model is None:
        return False
    change: ChangeDetectionResult = detect_model_changes(
        model=model,
        snapshot=snapshot,
        sql_analysis_enabled=False,
        query_change_tracking=True,
        full_refresh=False,
        expected_version_hash=version_identities.model_version_hashes.get(model_name),
        expected_metadata_json=version_identities.model_metadata_jsons.get(model_name),
    )
    return change.change_kind in {
        ChangeKind.FIRST_RUN,
        ChangeKind.QUERY_CHANGED,
        ChangeKind.CONFIG_CHANGED,
        ChangeKind.SCHEMA_CHANGED,
    }


def _seed_identity_changed(
    *,
    seed_name: str,
    snapshot: WarehouseSnapshot,
    version_identities: StandardModelVersionIdentities,
) -> bool:
    expected_hash: str | None = version_identities.seed_version_hashes.get(seed_name)
    if expected_hash is None:
        return False
    fingerprint: Fingerprint | None = snapshot.fingerprints.seeds.get(seed_name)
    return fingerprint is None or fingerprint.version_hash != expected_hash
