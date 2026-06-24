"""dbt reuse_from candidate resolution helpers."""

from __future__ import annotations

import json
from typing import cast

from sqlbuild.compiler.planner.main.reuse_policy import decide_reuse_for_node
from sqlbuild.compiler.planner.models import ReusePolicyNodeFacts
from sqlbuild.compiler.planner.types import StandardReuseDecisionKind
from sqlbuild.integrations.dbt.constants import (
    DBT_MANIFEST_CONFIG_KEY,
    DBT_MANIFEST_INCREMENTAL_STRATEGY_KEY,
    DBT_MANIFEST_MATERIALIZED_KEY,
    DBT_MANIFEST_META_KEY,
    DBT_MANIFEST_REUSE_CURSOR_KEY,
    DBT_MANIFEST_SQLBUILD_META_KEY,
    DBT_MATERIALIZATION_EPHEMERAL,
    DBT_MATERIALIZATION_INCREMENTAL,
    DBT_MATERIALIZATION_MICROBATCH,
    DBT_MATERIALIZATION_SNAPSHOT,
    DBT_MATERIALIZATION_TABLE,
    DBT_MATERIALIZATION_VIEW,
    DBT_REUSE_METADATA_CURSOR_COLUMN_KEY,
    DBT_REUSE_METADATA_DESTINATION_RELATION_KEY,
    DBT_REUSE_METADATA_EXECUTION_MODE_KEY,
    DBT_REUSE_METADATA_ORIGIN_RELATION_KEY,
    DBT_REUSE_METADATA_REUSE_MODE_KEY,
)
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
    DbtReuseExecutionMode,
    DbtReuseMode,
    DbtReusePlanAction,
    DbtReusePlanReason,
)

_SUPPORTED_PHYSICAL_MATERIALIZATIONS: frozenset[str] = frozenset(
    {
        DBT_MATERIALIZATION_TABLE,
        DBT_MATERIALIZATION_INCREMENTAL,
        DBT_MATERIALIZATION_MICROBATCH,
        DBT_MATERIALIZATION_SNAPSHOT,
    }
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
    effective_change_cache: dict[str, bool] = {}
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
                destination_relation_name=current_model.relation_name,
                origin_relation_name=reuse_model.relation_name,
                origin_database=reuse_model.database,
                origin_schema=reuse_model.schema,
                origin_name=reuse_model.alias or reuse_model.name,
                package_name=current_model.package_name,
                name=current_model.name,
                fqn=current_model.fqn,
                cursor_column=_model_reuse_cursor(model=current_model),
                current_definition_fingerprint=current_model.definition_fingerprint,
                origin_definition_fingerprint=reuse_model.definition_fingerprint,
                effective_definition_changed=_effective_definition_changed(
                    unique_id=unique_id,
                    current_manifest=current_manifest,
                    reuse_manifest=reuse_manifest,
                    cache=effective_change_cache,
                ),
            )
        )
    return DbtReuseCandidateResolution(candidates=tuple(candidates), skipped=tuple(skipped))


def _effective_definition_changed(
    *,
    unique_id: str,
    current_manifest: DbtManifestIndex,
    reuse_manifest: DbtManifestIndex,
    cache: dict[str, bool],
    visiting: frozenset[str] = frozenset(),
) -> bool:
    """Return whether a model or any transitive dbt-model upstream changed vs the reuse ref."""

    if unique_id in cache:
        return cache[unique_id]
    if unique_id in visiting:
        return False
    if _model_definition_changed(
        unique_id=unique_id,
        current_manifest=current_manifest,
        reuse_manifest=reuse_manifest,
    ):
        cache[unique_id] = True
        return True
    current_model: DbtManifestModel | None = current_manifest.models_by_unique_id.get(unique_id)
    if current_model is None:
        cache[unique_id] = False
        return False
    next_visiting: frozenset[str] = visiting | {unique_id}
    dependency_unique_id: str
    for dependency_unique_id in current_model.depends_on_nodes:
        if dependency_unique_id not in current_manifest.models_by_unique_id:
            continue
        if _effective_definition_changed(
            unique_id=dependency_unique_id,
            current_manifest=current_manifest,
            reuse_manifest=reuse_manifest,
            cache=cache,
            visiting=next_visiting,
        ):
            cache[unique_id] = True
            return True
    cache[unique_id] = False
    return False


def _model_definition_changed(
    *,
    unique_id: str,
    current_manifest: DbtManifestIndex,
    reuse_manifest: DbtManifestIndex,
) -> bool:
    current_model: DbtManifestModel | None = current_manifest.models_by_unique_id.get(unique_id)
    reuse_model: DbtManifestModel | None = reuse_manifest.models_by_unique_id.get(unique_id)
    if current_model is None or reuse_model is None:
        return True
    if not current_model.definition_fingerprint or not reuse_model.definition_fingerprint:
        return False
    return current_model.definition_fingerprint != reuse_model.definition_fingerprint


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
    strict: bool = False,
    trust_reuse_inputs: bool = False,
    current_project_affected_unique_ids: frozenset[str] = frozenset(),
    trusted_input_unique_ids: frozenset[str] = frozenset(),
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
                strict=strict,
                trust_reuse_inputs=trust_reuse_inputs,
                current_project_affected=(
                    candidate.unique_id in current_project_affected_unique_ids
                ),
                trusted_input=candidate.unique_id in trusted_input_unique_ids,
            )
        )
    skipped: DbtReuseCandidateSkip
    for skipped in candidate_resolution.skipped:
        entries.append(_skipped_entry(skip=skipped))
    return DbtReusePlanningResult(entries=tuple(entries))


def mark_missing_dbt_reuse_origin_relations(
    *,
    candidate_resolution: DbtReuseCandidateResolution,
    existing_origin_relation_keys: frozenset[tuple[str | None, str | None, str]],
) -> DbtReuseCandidateResolution:
    """Mark candidates whose production-origin relation does not exist."""

    candidates: list[DbtReuseCandidate] = []
    candidate: DbtReuseCandidate
    for candidate in candidate_resolution.candidates:
        candidates.append(
            DbtReuseCandidate(
                unique_id=candidate.unique_id,
                materialization=candidate.materialization,
                destination_relation_name=candidate.destination_relation_name,
                origin_relation_name=candidate.origin_relation_name,
                origin_database=candidate.origin_database,
                origin_schema=candidate.origin_schema,
                origin_name=candidate.origin_name,
                package_name=candidate.package_name,
                name=candidate.name,
                fqn=candidate.fqn,
                cursor_column=candidate.cursor_column,
                origin_relation_exists=(
                    candidate.origin_relation_key in existing_origin_relation_keys
                ),
                current_definition_fingerprint=candidate.current_definition_fingerprint,
                origin_definition_fingerprint=candidate.origin_definition_fingerprint,
                effective_definition_changed=candidate.effective_definition_changed,
            )
        )
    return DbtReuseCandidateResolution(
        candidates=tuple(candidates), skipped=candidate_resolution.skipped
    )


def _dbt_reuse_scope_unique_ids(*, plan: DbtInteropPlan) -> tuple[str, ...]:
    anchor_unique_ids: list[str] = []
    unique_ids: tuple[str, ...]
    for unique_ids in plan.selection.dbt_anchor_unique_ids_by_term.values():
        anchor_unique_ids.extend(unique_ids)
    model_plan_unique_ids: tuple[str, ...] = tuple(
        entry.unique_id for entry in (plan.dbt_model_plan.entries if plan.dbt_model_plan else ())
    )
    return _dedupe_preserving_order(
        values=(
            *plan.dbt_selected_unique_ids,
            *plan.selection.dbt_required_unique_ids,
            *anchor_unique_ids,
            *model_plan_unique_ids,
        )
    )


def _plan_reuse_candidate(
    *,
    candidate: DbtReuseCandidate,
    dbt_plan_entry: DbtModelPlanEntry | None,
    strict: bool,
    trust_reuse_inputs: bool,
    current_project_affected: bool,
    trusted_input: bool,
) -> DbtReusePlanEntry:
    if not candidate.origin_relation_exists:
        return DbtReusePlanEntry(
            unique_id=candidate.unique_id,
            action=DbtReusePlanAction.REBUILD,
            reason=DbtReusePlanReason.ORIGIN_RELATION_MISSING,
            materialization=candidate.materialization,
            destination_relation_name=candidate.destination_relation_name,
            origin_relation_name=candidate.origin_relation_name,
            cursor_column=candidate.cursor_column,
        )
    if dbt_plan_entry is None:
        return DbtReusePlanEntry(
            unique_id=candidate.unique_id,
            action=DbtReusePlanAction.BLOCKED,
            reason=DbtReusePlanReason.MANIFEST_NODE_MISSING,
            materialization=candidate.materialization,
            destination_relation_name=candidate.destination_relation_name,
            origin_relation_name=candidate.origin_relation_name,
            cursor_column=candidate.cursor_column,
        )
    if dbt_plan_entry.action == DbtModelPlanAction.BLOCKED:
        return _candidate_entry(
            candidate=candidate,
            dbt_plan_entry=dbt_plan_entry,
            action=DbtReusePlanAction.BLOCKED,
            reason=DbtReusePlanReason.SOURCE_FRESHNESS_BLOCK,
            current_project_affected=current_project_affected,
            trusted_input=trusted_input,
        )
    if dbt_plan_entry.action == DbtModelPlanAction.CURRENT:
        if _reuse_resume_metadata_invalid(candidate=candidate, dbt_plan_entry=dbt_plan_entry):
            return _candidate_entry(
                candidate=candidate,
                dbt_plan_entry=dbt_plan_entry,
                action=(
                    DbtReusePlanAction.COMPLETE_REUSE
                    if candidate.materialization == DBT_MATERIALIZATION_TABLE
                    else DbtReusePlanAction.SEEDED_REUSE
                ),
                reason=DbtReusePlanReason.REUSE_METADATA_INVALID,
                current_project_affected=current_project_affected,
                trusted_input=trusted_input,
            )
        return _candidate_entry(
            candidate=candidate,
            dbt_plan_entry=dbt_plan_entry,
            action=DbtReusePlanAction.CURRENT,
            reason=DbtReusePlanReason.DESTINATION_CURRENT,
            current_project_affected=current_project_affected,
            trusted_input=trusted_input,
        )
    if dbt_plan_entry.reason == DbtModelPlanReason.FULL_REFRESH:
        return _candidate_entry(
            candidate=candidate,
            dbt_plan_entry=dbt_plan_entry,
            action=DbtReusePlanAction.REBUILD,
            reason=DbtReusePlanReason.FULL_REFRESH,
            current_project_affected=current_project_affected,
            trusted_input=trusted_input,
        )
    effective_current_project_affected: bool = (
        current_project_affected
        or dbt_plan_entry.reason
        in {
            DbtModelPlanReason.CHECKSUM_CHANGED,
            DbtModelPlanReason.UPSTREAM_CHANGED,
            DbtModelPlanReason.SOURCE_FRESHNESS_CHANGED,
        }
    )
    decision: str = decide_reuse_for_node(
        ReusePolicyNodeFacts(
            expected_identity_present=dbt_plan_entry.expected_version_hash is not None,
            destination_identity_current=dbt_plan_entry.action == DbtModelPlanAction.CURRENT,
            destination_relation_exists=dbt_plan_entry.reason
            != DbtModelPlanReason.RELATION_MISSING,
            reuse_origin_identity_present=bool(candidate.origin_definition_fingerprint),
            reuse_origin_relation_exists=candidate.origin_relation_exists,
            reuse_origin_matches_expected=not candidate.definition_changed_from_origin,
            reuse_eligible_materialization=True,
            strict=strict,
            trust_reuse_inputs=trust_reuse_inputs,
            current_project_affected=effective_current_project_affected,
            trusted_input=trusted_input,
            source_freshness_stale=(
                dbt_plan_entry.reason == DbtModelPlanReason.SOURCE_FRESHNESS_CHANGED
            ),
        )
    )
    if decision not in {
        StandardReuseDecisionKind.REUSE_ELIGIBLE.value,
        StandardReuseDecisionKind.TRUSTED_REUSE_ELIGIBLE.value,
    }:
        return _candidate_entry(
            candidate=candidate,
            dbt_plan_entry=dbt_plan_entry,
            action=DbtReusePlanAction.REBUILD,
            reason=_reason_from_policy_decision(decision=decision),
            current_project_affected=effective_current_project_affected,
            trusted_input=trusted_input,
        )
    reuse_action: DbtReusePlanAction = (
        DbtReusePlanAction.COMPLETE_REUSE
        if candidate.materialization == DBT_MATERIALIZATION_TABLE
        else DbtReusePlanAction.SEEDED_REUSE
    )
    return _candidate_entry(
        candidate=candidate,
        dbt_plan_entry=dbt_plan_entry,
        action=reuse_action,
        reason=_reason_from_dbt_plan_reason(reason=dbt_plan_entry.reason),
        current_project_affected=effective_current_project_affected,
        trusted_input=(decision == StandardReuseDecisionKind.TRUSTED_REUSE_ELIGIBLE.value),
    )


def _candidate_entry(
    *,
    candidate: DbtReuseCandidate,
    dbt_plan_entry: DbtModelPlanEntry,
    action: DbtReusePlanAction,
    reason: DbtReusePlanReason,
    trusted_input: bool = False,
    current_project_affected: bool = False,
) -> DbtReusePlanEntry:
    return DbtReusePlanEntry(
        unique_id=candidate.unique_id,
        action=action,
        reason=reason,
        materialization=candidate.materialization,
        destination_relation_name=candidate.destination_relation_name,
        origin_relation_name=candidate.origin_relation_name,
        dbt_plan_action=dbt_plan_entry.action,
        dbt_plan_reason=dbt_plan_entry.reason,
        cursor_column=candidate.cursor_column,
        trusted_input=trusted_input,
        current_project_affected=current_project_affected,
    )


def _reason_from_policy_decision(*, decision: str) -> DbtReusePlanReason:
    if decision == StandardReuseDecisionKind.REUSE_ORIGIN_RELATION_MISSING.value:
        return DbtReusePlanReason.ORIGIN_RELATION_MISSING
    if decision == StandardReuseDecisionKind.REUSE_ORIGIN_VERSION_MISMATCH.value:
        return DbtReusePlanReason.DEFINITION_CHANGED
    if decision == StandardReuseDecisionKind.CURRENT_PROJECT_CHANGE.value:
        return DbtReusePlanReason.FINGERPRINT_CHANGED
    if decision == StandardReuseDecisionKind.REUSE_FROM_SOURCE_FRESHNESS_STALE.value:
        return DbtReusePlanReason.FINGERPRINT_CHANGED
    return DbtReusePlanReason.FINGERPRINT_CHANGED


def _reuse_resume_metadata_invalid(
    *, candidate: DbtReuseCandidate, dbt_plan_entry: DbtModelPlanEntry
) -> bool:
    metadata_json: str | None = dbt_plan_entry.previous_metadata_json
    if metadata_json is None:
        return False
    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    metadata: dict[str, object] = cast(dict[str, object], payload)
    if metadata.get(DBT_REUSE_METADATA_EXECUTION_MODE_KEY) != DbtReuseExecutionMode.REUSE:
        return False
    expected_reuse_mode: DbtReuseMode = _reuse_mode_for_materialization(
        materialization=candidate.materialization
    )
    relations_changed: bool = (
        metadata.get(DBT_REUSE_METADATA_REUSE_MODE_KEY) != expected_reuse_mode
        or metadata.get(DBT_REUSE_METADATA_ORIGIN_RELATION_KEY) != candidate.origin_relation_name
        or metadata.get(DBT_REUSE_METADATA_DESTINATION_RELATION_KEY)
        != candidate.destination_relation_name
    )
    if relations_changed:
        return True
    if expected_reuse_mode == DbtReuseMode.SEEDED:
        return metadata.get(DBT_REUSE_METADATA_CURSOR_COLUMN_KEY) != candidate.cursor_column
    return False


def _reuse_mode_for_materialization(*, materialization: str) -> DbtReuseMode:
    if materialization == DBT_MATERIALIZATION_TABLE:
        return DbtReuseMode.COMPLETE
    return DbtReuseMode.SEEDED


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
        return DbtReusePlanReason.DESTINATION_MISSING
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
    resource_type: object | None = model.payload.get("resource_type")
    if isinstance(resource_type, str) and resource_type.strip().lower() == (
        DBT_MATERIALIZATION_SNAPSHOT
    ):
        return DBT_MATERIALIZATION_SNAPSHOT
    config: object | None = model.payload.get(DBT_MANIFEST_CONFIG_KEY)
    if not isinstance(config, dict):
        return None
    config_mapping: dict[str, object] = cast(dict[str, object], config)
    materialized: object | None = config_mapping.get(DBT_MANIFEST_MATERIALIZED_KEY)
    if not isinstance(materialized, str) or not materialized.strip():
        return None
    materialization: str = materialized.strip().lower()
    incremental_strategy: object | None = config_mapping.get(DBT_MANIFEST_INCREMENTAL_STRATEGY_KEY)
    if (
        materialization == DBT_MATERIALIZATION_INCREMENTAL
        and incremental_strategy == DBT_MATERIALIZATION_MICROBATCH
    ):
        return DBT_MATERIALIZATION_MICROBATCH
    return materialization


def _model_reuse_cursor(*, model: DbtManifestModel) -> str | None:
    config: object | None = model.payload.get(DBT_MANIFEST_CONFIG_KEY)
    if not isinstance(config, dict):
        return None
    config_mapping: dict[str, object] = cast(dict[str, object], config)
    meta: object | None = config_mapping.get(DBT_MANIFEST_META_KEY)
    if not isinstance(meta, dict):
        return None
    meta_mapping: dict[str, object] = cast(dict[str, object], meta)
    sqlbuild_meta: object | None = meta_mapping.get(DBT_MANIFEST_SQLBUILD_META_KEY)
    if not isinstance(sqlbuild_meta, dict):
        return None
    sqlbuild_mapping: dict[str, object] = cast(dict[str, object], sqlbuild_meta)
    cursor: object | None = sqlbuild_mapping.get(DBT_MANIFEST_REUSE_CURSOR_KEY)
    if not isinstance(cursor, str) or not cursor.strip():
        return None
    return cursor.strip()


def _skip_reason_for_materialization(
    *, materialization: str | None
) -> DbtReuseCandidateSkipReason | None:
    if materialization == DBT_MATERIALIZATION_VIEW:
        return DbtReuseCandidateSkipReason.VIEW
    if materialization == DBT_MATERIALIZATION_EPHEMERAL:
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
