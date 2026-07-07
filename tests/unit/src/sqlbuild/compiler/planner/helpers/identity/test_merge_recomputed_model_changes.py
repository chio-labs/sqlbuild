"""Kind-merge matrix tests for merge_recomputed_model_changes."""

import pytest

from sqlbuild.compiler.planner.helpers.identity.honest import merge_recomputed_model_changes
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ChangeDetectionResult,
    PlannerChangeResults,
    PlannerResolvedActions,
    ResolvedModelAction,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind
from tests.unit.src.sqlbuild.compiler.planner.helpers.identity._test_types import (
    MergeRecomputedModelChangesTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.identity.helpers import (
    MERGE_MODEL_NAME,
    MERGE_RECOMPUTED_HASH,
    build_recomputed_models,
    build_resolved_actions,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MergeRecomputedModelChangesTestCase(
            description="first_run keeps resolved change when no recomputed change exists",
            resolved_change_kind=ChangeKind.FIRST_RUN,
            recomputed_change_kind=None,
            expected_change_kind=ChangeKind.FIRST_RUN,
            expected_backfill_action=BackfillAction.BOUNDED,
            expected_version_hash="resolved-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="query_changed keeps resolved change when no recomputed change exists",
            resolved_change_kind=ChangeKind.QUERY_CHANGED,
            recomputed_change_kind=None,
            expected_change_kind=ChangeKind.QUERY_CHANGED,
            expected_backfill_action=BackfillAction.BOUNDED,
            expected_version_hash="resolved-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="config_changed keeps resolved change when no recomputed change exists",
            resolved_change_kind=ChangeKind.CONFIG_CHANGED,
            recomputed_change_kind=None,
            expected_change_kind=ChangeKind.CONFIG_CHANGED,
            expected_backfill_action=BackfillAction.BOUNDED,
            expected_version_hash="resolved-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="schema_changed keeps resolved change when no recomputed change exists",
            resolved_change_kind=ChangeKind.SCHEMA_CHANGED,
            recomputed_change_kind=None,
            expected_change_kind=ChangeKind.SCHEMA_CHANGED,
            expected_backfill_action=BackfillAction.BOUNDED,
            expected_version_hash="resolved-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="run_despite_unchanged keeps resolved change when no recomputed change exists",
            resolved_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
            recomputed_change_kind=None,
            expected_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
            expected_backfill_action=BackfillAction.BOUNDED,
            expected_version_hash="resolved-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="no_change keeps resolved change when no recomputed change exists",
            resolved_change_kind=ChangeKind.NO_CHANGE,
            recomputed_change_kind=None,
            expected_change_kind=ChangeKind.NO_CHANGE,
            expected_backfill_action=BackfillAction.BOUNDED,
            expected_version_hash="resolved-hash",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_no_recomputed_change_when_merging_then_keeps_resolved_change(
    test_case: MergeRecomputedModelChangesTestCase,
) -> None:
    resolved_actions: PlannerResolvedActions = build_resolved_actions(
        test_case.resolved_change_kind
    )

    merged: PlannerResolvedActions = merge_recomputed_model_changes(
        resolved_actions=resolved_actions,
        changes=PlannerChangeResults(models={}, functions={}),
    )

    merged_action: ResolvedModelAction = merged.models[MERGE_MODEL_NAME]
    assert merged_action.change.change_kind == test_case.expected_change_kind
    assert merged_action.change.backfill.action == test_case.expected_backfill_action
    assert merged_action.change.fingerprint_version_hash == test_case.expected_version_hash
    assert merged_action.backfill == BackfillResult(action=BackfillAction.FULL)
    assert set(merged.models) == set(resolved_actions.models)


@pytest.mark.parametrize(
    "test_case",
    [
        MergeRecomputedModelChangesTestCase(
            description="first_run adopts recomputed no_change",
            resolved_change_kind=ChangeKind.FIRST_RUN,
            recomputed_change_kind=ChangeKind.NO_CHANGE,
            expected_change_kind=ChangeKind.NO_CHANGE,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="first_run adopts recomputed query_changed",
            resolved_change_kind=ChangeKind.FIRST_RUN,
            recomputed_change_kind=ChangeKind.QUERY_CHANGED,
            expected_change_kind=ChangeKind.QUERY_CHANGED,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="query_changed adopts recomputed no_change",
            resolved_change_kind=ChangeKind.QUERY_CHANGED,
            recomputed_change_kind=ChangeKind.NO_CHANGE,
            expected_change_kind=ChangeKind.NO_CHANGE,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="query_changed adopts recomputed query_changed",
            resolved_change_kind=ChangeKind.QUERY_CHANGED,
            recomputed_change_kind=ChangeKind.QUERY_CHANGED,
            expected_change_kind=ChangeKind.QUERY_CHANGED,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="config_changed adopts recomputed no_change",
            resolved_change_kind=ChangeKind.CONFIG_CHANGED,
            recomputed_change_kind=ChangeKind.NO_CHANGE,
            expected_change_kind=ChangeKind.NO_CHANGE,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="config_changed adopts recomputed query_changed",
            resolved_change_kind=ChangeKind.CONFIG_CHANGED,
            recomputed_change_kind=ChangeKind.QUERY_CHANGED,
            expected_change_kind=ChangeKind.QUERY_CHANGED,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="schema_changed adopts recomputed no_change",
            resolved_change_kind=ChangeKind.SCHEMA_CHANGED,
            recomputed_change_kind=ChangeKind.NO_CHANGE,
            expected_change_kind=ChangeKind.NO_CHANGE,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="schema_changed adopts recomputed query_changed",
            resolved_change_kind=ChangeKind.SCHEMA_CHANGED,
            recomputed_change_kind=ChangeKind.QUERY_CHANGED,
            expected_change_kind=ChangeKind.QUERY_CHANGED,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="run_despite_unchanged survives recomputed no_change with resolved backfill",
            resolved_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
            recomputed_change_kind=ChangeKind.NO_CHANGE,
            expected_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
            expected_backfill_action=BackfillAction.BOUNDED,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="run_despite_unchanged adopts recomputed query_changed",
            resolved_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
            recomputed_change_kind=ChangeKind.QUERY_CHANGED,
            expected_change_kind=ChangeKind.QUERY_CHANGED,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="no_change adopts recomputed no_change",
            resolved_change_kind=ChangeKind.NO_CHANGE,
            recomputed_change_kind=ChangeKind.NO_CHANGE,
            expected_change_kind=ChangeKind.NO_CHANGE,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
        MergeRecomputedModelChangesTestCase(
            description="no_change adopts recomputed query_changed",
            resolved_change_kind=ChangeKind.NO_CHANGE,
            recomputed_change_kind=ChangeKind.QUERY_CHANGED,
            expected_change_kind=ChangeKind.QUERY_CHANGED,
            expected_backfill_action=BackfillAction.FORWARD_ONLY,
            expected_version_hash="recomputed-hash",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recomputed_change_when_merging_then_adopts_recomputed_change(
    test_case: MergeRecomputedModelChangesTestCase,
) -> None:
    assert test_case.recomputed_change_kind is not None
    resolved_actions: PlannerResolvedActions = build_resolved_actions(
        test_case.resolved_change_kind
    )
    recomputed_models: dict[str, ChangeDetectionResult] = build_recomputed_models(
        test_case.recomputed_change_kind
    )

    merged: PlannerResolvedActions = merge_recomputed_model_changes(
        resolved_actions=resolved_actions,
        changes=PlannerChangeResults(models=recomputed_models, functions={}),
    )

    merged_action: ResolvedModelAction = merged.models[MERGE_MODEL_NAME]
    assert merged_action.change.change_kind == test_case.expected_change_kind
    assert merged_action.change.backfill.action == test_case.expected_backfill_action
    assert merged_action.change.fingerprint_version_hash == test_case.expected_version_hash
    assert merged_action.change.fingerprint_version_hash == MERGE_RECOMPUTED_HASH
    assert merged_action.backfill == BackfillResult(action=BackfillAction.FULL)
    assert set(merged.models) == set(resolved_actions.models)
