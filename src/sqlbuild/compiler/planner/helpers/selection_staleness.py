"""Selection-aware stale warning helpers for standard planning."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.changes.detect import detect_model_changes
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    PlannerChangeResults,
    PlannerScope,
    PlanWarning,
    StandardModelVersionIdentities,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import ChangeKind, WarningSeverity
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult

_WARNING_TRIGGER_LIMIT: int = 5


def build_stale_out_of_selection_warnings(
    *,
    original_scope: PlannerScope,
    execution_scope: PlannerScope,
    changes: PlannerChangeResults,
    snapshot: WarehouseSnapshot,
    version_identities: StandardModelVersionIdentities,
    source_freshness: StandardSourceFreshnessPlanningResult | None,
) -> tuple[PlanWarning, ...]:
    """Warn for selected models stale through changed upstreams outside the run set."""

    run_model_names: frozenset[str] = frozenset(
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
    warnings: list[PlanWarning] = []
    key: CompiledObjectKey
    for key in original_scope.selected_keys:
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        triggers: tuple[str, ...] = _changed_upstream_names(
            model_key=key,
            original_scope=original_scope,
            run_model_names=run_model_names,
            run_seed_names=run_seed_names,
            run_source_names=run_source_names,
            changes=changes,
            snapshot=snapshot,
            version_identities=version_identities,
            source_freshness=source_freshness,
        )
        if not triggers:
            continue
        warnings.append(
            PlanWarning(
                model_name=key.name,
                severity=WarningSeverity.WARNING,
                message=(
                    f"selected model '{key.name}' is stale: upstream "
                    f"{_format_trigger_names(triggers)}; "
                    "use a closure selector (for example +model) to incorporate it"
                ),
            )
        )
    return tuple(warnings)


def _changed_upstream_names(
    *,
    model_key: CompiledObjectKey,
    original_scope: PlannerScope,
    run_model_names: frozenset[str],
    run_seed_names: frozenset[str],
    run_source_names: frozenset[str],
    changes: PlannerChangeResults,
    snapshot: WarehouseSnapshot,
    version_identities: StandardModelVersionIdentities,
    source_freshness: StandardSourceFreshnessPlanningResult | None,
) -> tuple[str, ...]:
    names: set[str] = set()
    visited: set[CompiledObjectKey] = set()

    def visit(upstream_key: CompiledObjectKey) -> bool:
        if upstream_key in visited:
            return False
        visited.add(upstream_key)
        if upstream_key.resource_type == CompiledResourceType.MODEL:
            in_run_set: bool = upstream_key.name in run_model_names
            own_changed: bool = _model_own_identity_changed(
                model_name=upstream_key.name,
                original_scope=original_scope,
                changes=changes,
                snapshot=snapshot,
                version_identities=version_identities,
            )
            if own_changed and not in_run_set:
                names.add(upstream_key.name)
                return True
            ancestor_stale: bool = False
            parent_key: CompiledObjectKey
            for parent_key in original_scope.upstream_deps.get(upstream_key, ()):
                ancestor_stale = visit(parent_key) or ancestor_stale
                if _run_parent_changed(
                    parent_key=parent_key,
                    run_model_names=run_model_names,
                    run_seed_names=run_seed_names,
                    run_source_names=run_source_names,
                    original_scope=original_scope,
                    changes=changes,
                    snapshot=snapshot,
                    version_identities=version_identities,
                    source_freshness=source_freshness,
                ):
                    ancestor_stale = True
            if ancestor_stale and not in_run_set:
                names.add(upstream_key.name)
                return True
            return ancestor_stale
        if upstream_key.resource_type == CompiledResourceType.SEED:
            changed: bool = _seed_identity_changed(
                seed_name=upstream_key.name,
                snapshot=snapshot,
                version_identities=version_identities,
            )
            if changed and upstream_key.name not in run_seed_names:
                names.add(upstream_key.name)
            return changed
        if upstream_key.resource_type == CompiledResourceType.SOURCE:
            changed = _source_freshness_changed(
                source_name=upstream_key.name,
                source_freshness=source_freshness,
            )
            if changed and upstream_key.name not in run_source_names:
                names.add(upstream_key.name)
            return changed
        return False

    upstream_key: CompiledObjectKey
    for upstream_key in original_scope.upstream_deps.get(model_key, ()):
        visit(upstream_key)
    return tuple(sorted(names))


def _run_parent_changed(
    *,
    parent_key: CompiledObjectKey,
    run_model_names: frozenset[str],
    run_seed_names: frozenset[str],
    run_source_names: frozenset[str],
    original_scope: PlannerScope,
    changes: PlannerChangeResults,
    snapshot: WarehouseSnapshot,
    version_identities: StandardModelVersionIdentities,
    source_freshness: StandardSourceFreshnessPlanningResult | None,
) -> bool:
    if parent_key.resource_type == CompiledResourceType.MODEL:
        return parent_key.name in run_model_names and _model_own_identity_changed(
            model_name=parent_key.name,
            original_scope=original_scope,
            changes=changes,
            snapshot=snapshot,
            version_identities=version_identities,
        )
    if parent_key.resource_type == CompiledResourceType.SEED:
        return parent_key.name in run_seed_names and _seed_identity_changed(
            seed_name=parent_key.name,
            snapshot=snapshot,
            version_identities=version_identities,
        )
    if parent_key.resource_type == CompiledResourceType.SOURCE:
        return parent_key.name in run_source_names and _source_freshness_changed(
            source_name=parent_key.name,
            source_freshness=source_freshness,
        )
    return False


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


def _source_freshness_changed(
    *, source_name: str, source_freshness: StandardSourceFreshnessPlanningResult | None
) -> bool:
    if source_freshness is None:
        return False
    return any(
        identity.source_name == source_name for identity in source_freshness.changed_identities
    )


def _format_trigger_names(names: tuple[str, ...]) -> str:
    displayed: tuple[str, ...] = names[:_WARNING_TRIGGER_LIMIT]
    suffix: str = ""
    if len(names) > _WARNING_TRIGGER_LIMIT:
        suffix = f" +{len(names) - _WARNING_TRIGGER_LIMIT} more"
    return (
        ", ".join(f"{name} changed but will not be rebuilt or is stale" for name in displayed)
        + suffix
    )
