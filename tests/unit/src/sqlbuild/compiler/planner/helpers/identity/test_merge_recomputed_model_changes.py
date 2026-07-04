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

_MODEL_NAME = "orders"
_RESOLVED_HASH = "resolved-hash"
_RECOMPUTED_HASH = "recomputed-hash"

TEST_CASES = [
    MergeRecomputedModelChangesTestCase(
        description="first_run keeps resolved change when no recomputed change exists",
        resolved_change_kind=ChangeKind.FIRST_RUN,
        recomputed_change_kind=None,
        expected_change_kind=ChangeKind.FIRST_RUN,
        expected_backfill_action=BackfillAction.BOUNDED,
        expected_version_hash=_RESOLVED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="first_run adopts recomputed no_change",
        resolved_change_kind=ChangeKind.FIRST_RUN,
        recomputed_change_kind=ChangeKind.NO_CHANGE,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="first_run adopts recomputed query_changed",
        resolved_change_kind=ChangeKind.FIRST_RUN,
        recomputed_change_kind=ChangeKind.QUERY_CHANGED,
        expected_change_kind=ChangeKind.QUERY_CHANGED,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="query_changed keeps resolved change when no recomputed change exists",
        resolved_change_kind=ChangeKind.QUERY_CHANGED,
        recomputed_change_kind=None,
        expected_change_kind=ChangeKind.QUERY_CHANGED,
        expected_backfill_action=BackfillAction.BOUNDED,
        expected_version_hash=_RESOLVED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="query_changed adopts recomputed no_change",
        resolved_change_kind=ChangeKind.QUERY_CHANGED,
        recomputed_change_kind=ChangeKind.NO_CHANGE,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="query_changed adopts recomputed query_changed",
        resolved_change_kind=ChangeKind.QUERY_CHANGED,
        recomputed_change_kind=ChangeKind.QUERY_CHANGED,
        expected_change_kind=ChangeKind.QUERY_CHANGED,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="config_changed keeps resolved change when no recomputed change exists",
        resolved_change_kind=ChangeKind.CONFIG_CHANGED,
        recomputed_change_kind=None,
        expected_change_kind=ChangeKind.CONFIG_CHANGED,
        expected_backfill_action=BackfillAction.BOUNDED,
        expected_version_hash=_RESOLVED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="config_changed adopts recomputed no_change",
        resolved_change_kind=ChangeKind.CONFIG_CHANGED,
        recomputed_change_kind=ChangeKind.NO_CHANGE,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="config_changed adopts recomputed query_changed",
        resolved_change_kind=ChangeKind.CONFIG_CHANGED,
        recomputed_change_kind=ChangeKind.QUERY_CHANGED,
        expected_change_kind=ChangeKind.QUERY_CHANGED,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="schema_changed keeps resolved change when no recomputed change exists",
        resolved_change_kind=ChangeKind.SCHEMA_CHANGED,
        recomputed_change_kind=None,
        expected_change_kind=ChangeKind.SCHEMA_CHANGED,
        expected_backfill_action=BackfillAction.BOUNDED,
        expected_version_hash=_RESOLVED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="schema_changed adopts recomputed no_change",
        resolved_change_kind=ChangeKind.SCHEMA_CHANGED,
        recomputed_change_kind=ChangeKind.NO_CHANGE,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="schema_changed adopts recomputed query_changed",
        resolved_change_kind=ChangeKind.SCHEMA_CHANGED,
        recomputed_change_kind=ChangeKind.QUERY_CHANGED,
        expected_change_kind=ChangeKind.QUERY_CHANGED,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="run_despite_unchanged keeps resolved change when no recomputed change exists",
        resolved_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
        recomputed_change_kind=None,
        expected_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
        expected_backfill_action=BackfillAction.BOUNDED,
        expected_version_hash=_RESOLVED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="run_despite_unchanged survives recomputed no_change with resolved backfill",
        resolved_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
        recomputed_change_kind=ChangeKind.NO_CHANGE,
        expected_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
        expected_backfill_action=BackfillAction.BOUNDED,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="run_despite_unchanged adopts recomputed query_changed",
        resolved_change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
        recomputed_change_kind=ChangeKind.QUERY_CHANGED,
        expected_change_kind=ChangeKind.QUERY_CHANGED,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="no_change keeps resolved change when no recomputed change exists",
        resolved_change_kind=ChangeKind.NO_CHANGE,
        recomputed_change_kind=None,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.BOUNDED,
        expected_version_hash=_RESOLVED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="no_change adopts recomputed no_change",
        resolved_change_kind=ChangeKind.NO_CHANGE,
        recomputed_change_kind=ChangeKind.NO_CHANGE,
        expected_change_kind=ChangeKind.NO_CHANGE,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
    MergeRecomputedModelChangesTestCase(
        description="no_change adopts recomputed query_changed",
        resolved_change_kind=ChangeKind.NO_CHANGE,
        recomputed_change_kind=ChangeKind.QUERY_CHANGED,
        expected_change_kind=ChangeKind.QUERY_CHANGED,
        expected_backfill_action=BackfillAction.FORWARD_ONLY,
        expected_version_hash=_RECOMPUTED_HASH,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_kind_merge_matrix_cell_when_merging_recomputed_changes_then_returns_expected_change(
    test_case: MergeRecomputedModelChangesTestCase,
) -> None:
    resolved_change = ChangeDetectionResult(
        model_name=_MODEL_NAME,
        change_kind=test_case.resolved_change_kind,
        fingerprint_version_hash=_RESOLVED_HASH,
        backfill=BackfillResult(action=BackfillAction.BOUNDED, duration="7d"),
    )
    resolved_actions = PlannerResolvedActions(
        models={
            _MODEL_NAME: ResolvedModelAction(
                change=resolved_change,
                backfill=BackfillResult(action=BackfillAction.FULL),
            )
        }
    )
    recomputed_models: dict[str, ChangeDetectionResult] = {}
    if test_case.recomputed_change_kind is not None:
        recomputed_models[_MODEL_NAME] = ChangeDetectionResult(
            model_name=_MODEL_NAME,
            change_kind=test_case.recomputed_change_kind,
            fingerprint_version_hash=_RECOMPUTED_HASH,
            backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
        )

    merged = merge_recomputed_model_changes(
        resolved_actions=resolved_actions,
        changes=PlannerChangeResults(models=recomputed_models, functions={}),
    )

    merged_action = merged.models[_MODEL_NAME]
    assert merged_action.change.change_kind == test_case.expected_change_kind
    assert merged_action.change.backfill.action == test_case.expected_backfill_action
    assert merged_action.change.fingerprint_version_hash == test_case.expected_version_hash
    assert merged_action.backfill == BackfillResult(action=BackfillAction.FULL)
    assert set(merged.models) == set(resolved_actions.models)
