"""dbt reuse_from candidate resolution helpers."""

from __future__ import annotations

from typing import cast

from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtInteropPlan,
    DbtModelPlanEntry,
    DbtModelPlanningResult,
    DbtReuseCandidate,
    DbtReuseCandidateResolution,
    DbtReuseCandidateSkip,
    DbtReusePlanEntry,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.types import (
    DbtModelPlanAction,
    DbtModelPlanReason,
    DbtReuseCandidateSkipReason,
    DbtReusePlanAction,
    DbtReusePlanReason,
)

_SUPPORTED_PHYSICAL_MATERIALIZATIONS: frozenset[str] = frozenset(
    {"table", "incremental", "microbatch", "snapshot"}
)


def resolve_dbt_reuse_candidates(
    *,
    current_manifest: DbtManifestIndex,
    reuse_manifest: DbtManifestIndex,
    scoped_unique_ids: tuple[str, ...],
) -> DbtReuseCandidateResolution:
    """Resolve physical dbt reuse candidates inside the supplied selection scope."""

    candidates: list[DbtReuseCandidate] = []
    skipped: list[DbtReuseCandidateSkip] = []
    unique_id: str
    for unique_id in _dedupe_preserving_order(values=scoped_unique_ids):
        current_model: DbtManifestModel | None = current_manifest.models_by_unique_id.get(unique_id)
        if current_model is None:
            skipped.append(
                DbtReuseCandidateSkip(
                    unique_id=unique_id,
                    reason=DbtReuseCandidateSkipReason.CURRENT_MANIFEST_MISSING,
                )
            )
            continue

        reuse_model: DbtManifestModel | None = reuse_manifest.models_by_unique_id.get(unique_id)
        if reuse_model is None:
            skipped.append(
                DbtReuseCandidateSkip(
                    unique_id=unique_id,
                    reason=DbtReuseCandidateSkipReason.REUSE_MANIFEST_MISSING,
                    materialization=_model_materialization(model=current_model),
                    name=current_model.name,
                )
            )
            continue

        materialization: str | None = _model_materialization(model=current_model)
        skip_reason: DbtReuseCandidateSkipReason | None = _skip_reason_for_materialization(
            materialization=materialization
        )
        if skip_reason is not None:
            skipped.append(
                DbtReuseCandidateSkip(
                    unique_id=unique_id,
                    reason=skip_reason,
                    materialization=materialization,
                    name=current_model.name,
                )
            )
            continue

        candidates.append(
            DbtReuseCandidate(
                unique_id=unique_id,
                materialization=materialization or "",
                current_relation_name=current_model.relation_name,
                reuse_relation_name=reuse_model.relation_name,
                package_name=current_model.package_name,
                name=current_model.name,
                fqn=current_model.fqn,
            )
        )
    return DbtReuseCandidateResolution(candidates=tuple(candidates), skipped=tuple(skipped))


def resolve_dbt_reuse_candidates_for_plan(
    *,
    current_manifest: DbtManifestIndex,
    reuse_manifest: DbtManifestIndex,
    plan: DbtInteropPlan,
) -> DbtReuseCandidateResolution:
    """Resolve reuse candidates for the dbt nodes selected or required by a plan."""

    scoped_unique_ids: tuple[str, ...] = _dbt_reuse_scope_unique_ids(plan=plan)
    return resolve_dbt_reuse_candidates(
        current_manifest=current_manifest,
        reuse_manifest=reuse_manifest,
        scoped_unique_ids=scoped_unique_ids,
    )


def build_dbt_reuse_planning_result(
    *,
    candidate_resolution: DbtReuseCandidateResolution,
    dbt_model_plan: DbtModelPlanningResult,
) -> DbtReusePlanningResult:
    """Classify scoped dbt reuse candidates using existing dbt model planning state."""

    plan_entries_by_unique_id: dict[str, DbtModelPlanEntry] = {
        entry.unique_id: entry for entry in dbt_model_plan.entries
    }
    entries: list[DbtReusePlanEntry] = []
    candidate: DbtReuseCandidate
    for candidate in candidate_resolution.candidates:
        entries.append(
            _plan_reuse_candidate(
                candidate=candidate,
                dbt_plan_entry=plan_entries_by_unique_id.get(candidate.unique_id),
            )
        )
    skipped: DbtReuseCandidateSkip
    for skipped in candidate_resolution.skipped:
        entries.append(_skipped_entry(skip=skipped))
    return DbtReusePlanningResult(entries=tuple(entries))


def _dbt_reuse_scope_unique_ids(*, plan: DbtInteropPlan) -> tuple[str, ...]:
    anchor_unique_ids: list[str] = []
    unique_ids: tuple[str, ...]
    for unique_ids in plan.selection.dbt_anchor_unique_ids_by_term.values():
        anchor_unique_ids.extend(unique_ids)
    return _dedupe_preserving_order(
        values=(
            *plan.dbt_selected_unique_ids,
            *plan.selection.dbt_required_unique_ids,
            *anchor_unique_ids,
        )
    )


def _plan_reuse_candidate(
    *, candidate: DbtReuseCandidate, dbt_plan_entry: DbtModelPlanEntry | None
) -> DbtReusePlanEntry:
    if dbt_plan_entry is None:
        return DbtReusePlanEntry(
            unique_id=candidate.unique_id,
            action=DbtReusePlanAction.BLOCKED,
            reason=DbtReusePlanReason.MANIFEST_NODE_MISSING,
            materialization=candidate.materialization,
            current_relation_name=candidate.current_relation_name,
            reuse_relation_name=candidate.reuse_relation_name,
        )
    if dbt_plan_entry.action == DbtModelPlanAction.BLOCKED:
        return _candidate_entry(
            candidate=candidate,
            dbt_plan_entry=dbt_plan_entry,
            action=DbtReusePlanAction.BLOCKED,
            reason=DbtReusePlanReason.SOURCE_FRESHNESS_BLOCK,
        )
    if dbt_plan_entry.action == DbtModelPlanAction.CURRENT:
        return _candidate_entry(
            candidate=candidate,
            dbt_plan_entry=dbt_plan_entry,
            action=DbtReusePlanAction.CURRENT,
            reason=DbtReusePlanReason.TARGET_CURRENT,
        )
    if dbt_plan_entry.reason == DbtModelPlanReason.FULL_REFRESH:
        return _candidate_entry(
            candidate=candidate,
            dbt_plan_entry=dbt_plan_entry,
            action=DbtReusePlanAction.REBUILD,
            reason=DbtReusePlanReason.FULL_REFRESH,
        )
    reuse_action: DbtReusePlanAction = (
        DbtReusePlanAction.COMPLETE_REUSE
        if candidate.materialization == "table"
        else DbtReusePlanAction.SEEDED_REUSE
    )
    return _candidate_entry(
        candidate=candidate,
        dbt_plan_entry=dbt_plan_entry,
        action=reuse_action,
        reason=_reason_from_dbt_plan_reason(reason=dbt_plan_entry.reason),
    )


def _candidate_entry(
    *,
    candidate: DbtReuseCandidate,
    dbt_plan_entry: DbtModelPlanEntry,
    action: DbtReusePlanAction,
    reason: DbtReusePlanReason,
) -> DbtReusePlanEntry:
    return DbtReusePlanEntry(
        unique_id=candidate.unique_id,
        action=action,
        reason=reason,
        materialization=candidate.materialization,
        current_relation_name=candidate.current_relation_name,
        reuse_relation_name=candidate.reuse_relation_name,
        dbt_plan_action=dbt_plan_entry.action,
        dbt_plan_reason=dbt_plan_entry.reason,
    )


def _skipped_entry(*, skip: DbtReuseCandidateSkip) -> DbtReusePlanEntry:
    return DbtReusePlanEntry(
        unique_id=skip.unique_id,
        action=DbtReusePlanAction.SKIPPED,
        reason=_reason_from_skip_reason(reason=skip.reason),
        materialization=skip.materialization,
        skip_reason=skip.reason,
    )


def _reason_from_dbt_plan_reason(*, reason: DbtModelPlanReason) -> DbtReusePlanReason:
    if reason == DbtModelPlanReason.FIRST_RUN:
        return DbtReusePlanReason.FINGERPRINT_MISSING
    if reason == DbtModelPlanReason.RELATION_MISSING:
        return DbtReusePlanReason.TARGET_MISSING
    if reason in {DbtModelPlanReason.CHECKSUM_CHANGED, DbtModelPlanReason.UPSTREAM_CHANGED}:
        return DbtReusePlanReason.FINGERPRINT_CHANGED
    return DbtReusePlanReason.FINGERPRINT_CHANGED


def _reason_from_skip_reason(*, reason: DbtReuseCandidateSkipReason) -> DbtReusePlanReason:
    if reason in {
        DbtReuseCandidateSkipReason.CURRENT_MANIFEST_MISSING,
        DbtReuseCandidateSkipReason.REUSE_MANIFEST_MISSING,
    }:
        return DbtReusePlanReason.MANIFEST_NODE_MISSING
    return DbtReusePlanReason.NON_PHYSICAL_RESOURCE


def _model_materialization(*, model: DbtManifestModel) -> str | None:
    config: object | None = model.payload.get("config")
    if not isinstance(config, dict):
        return None
    config_mapping: dict[str, object] = cast(dict[str, object], config)
    materialized: object | None = config_mapping.get("materialized")
    if not isinstance(materialized, str) or not materialized.strip():
        return None
    materialization: str = materialized.strip().lower()
    incremental_strategy: object | None = config_mapping.get("incremental_strategy")
    if materialization == "incremental" and incremental_strategy == "microbatch":
        return "microbatch"
    return materialization


def _skip_reason_for_materialization(
    *, materialization: str | None
) -> DbtReuseCandidateSkipReason | None:
    if materialization == "view":
        return DbtReuseCandidateSkipReason.VIEW
    if materialization == "ephemeral":
        return DbtReuseCandidateSkipReason.EPHEMERAL
    if materialization not in _SUPPORTED_PHYSICAL_MATERIALIZATIONS:
        return DbtReuseCandidateSkipReason.UNSUPPORTED_MATERIALIZATION
    return None


def _dedupe_preserving_order(*, values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    value: str
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
