from __future__ import annotations

from typing import Any, cast

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.pruning.standard_scope import (
    build_standard_identity_stale_model_names,
    mark_direct_parent_run_actions,
    mark_version_identity_stale_actions,
    prune_standard_unchanged_scope,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ChangeDetectionResult,
    FunctionChangeResult,
    PlannerChangeResults,
    PlannerResolvedActions,
    PlannerScope,
    ResolvedModelAction,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind, PlanReason
from sqlbuild.compiler.source_freshness.models import (
    StandardSourceFreshnessPlanningResult,
    StandardSourceFreshnessPropagationResult,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    DirectIdentityStaleModelNamesTestCase,
    DirectParentRunActionTestCase,
    MarkVersionIdentityStaleActionsTestCase,
    PruneUnchangedScopeTestCase,
)

MODEL_UNCHANGED: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="unchanged_model",
)
MODEL_CHANGED: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="changed_model",
)
MODEL_BACKFILL: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="backfill_model",
)
FUNCTION_UNCHANGED: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.UDF,
    name="unchanged_function",
)
FUNCTION_CHANGED: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.UDF,
    name="changed_function",
)
SOURCE_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.SOURCE,
    name="raw_orders",
)
SEED_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.SEED,
    name="seed_orders",
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectIdentityStaleModelNamesTestCase(
            description="returns models with missing or mismatched built identities",
            expected_version_hashes={
                "current_model": "current_hash",
                "stale_model": "new_hash",
                "missing_model": "first_hash",
            },
            built_version_hashes={
                "current_model": "current_hash",
                "stale_model": "old_hash",
                "missing_model": None,
            },
            expected_stale_model_names=frozenset({"stale_model", "missing_model"}),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_identity_hashes_when_collecting_stale_models_then_returns_missing_and_mismatched(
    test_case: DirectIdentityStaleModelNamesTestCase,
) -> None:
    scope: PlannerScope = PlannerScope(
        upstream_deps={},
        downstream_deps={},
        all_keys={},
        models_by_name=cast(
            dict[str, Any],
            {"current_model": None, "stale_model": None, "missing_model": None},
        ),
        selected_keys=frozenset(),
        execution_order=(),
    )

    result: frozenset[str] = build_standard_identity_stale_model_names(
        scope=scope,
        expected_version_hashes=test_case.expected_version_hashes,
        built_version_hashes=test_case.built_version_hashes,
    )

    assert result == test_case.expected_stale_model_names


@pytest.mark.parametrize(
    "test_case",
    [
        PruneUnchangedScopeTestCase(
            description="keeps stale SQL keys and non-model resources",
            scope=PlannerScope(
                upstream_deps={},
                downstream_deps={},
                all_keys={},
                models_by_name={},
                selected_keys=frozenset(
                    {
                        MODEL_UNCHANGED,
                        MODEL_CHANGED,
                        MODEL_BACKFILL,
                        FUNCTION_UNCHANGED,
                        FUNCTION_CHANGED,
                        SEED_KEY,
                    }
                ),
                execution_order=(),
            ),
            expected_selected_keys=frozenset(
                {MODEL_CHANGED, MODEL_BACKFILL, FUNCTION_CHANGED, SEED_KEY}
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mixed_change_results_when_pruning_unchanged_scope_then_keeps_only_stale_sql_keys(
    test_case: PruneUnchangedScopeTestCase,
) -> None:
    result: PlannerScope = prune_standard_unchanged_scope(
        scope=test_case.scope,
        changes=PlannerChangeResults(
            models={
                "unchanged_model": ChangeDetectionResult(
                    model_name="unchanged_model",
                    change_kind=ChangeKind.NO_CHANGE,
                ),
                "changed_model": ChangeDetectionResult(
                    model_name="changed_model",
                    change_kind=ChangeKind.QUERY_CHANGED,
                ),
                "backfill_model": ChangeDetectionResult(
                    model_name="backfill_model",
                    change_kind=ChangeKind.NO_CHANGE,
                ),
            },
            functions={
                "unchanged_function": FunctionChangeResult(
                    fingerprint_sql="amount > 0",
                ),
                "changed_function": FunctionChangeResult(
                    fingerprint_sql="amount > 1",
                    reason=PlanReason.QUERY_CHANGED,
                ),
            },
        ),
        resolved_actions=PlannerResolvedActions(
            models={
                "unchanged_model": ResolvedModelAction(
                    change=ChangeDetectionResult(
                        model_name="unchanged_model",
                        change_kind=ChangeKind.NO_CHANGE,
                    ),
                    backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
                ),
                "changed_model": ResolvedModelAction(
                    change=ChangeDetectionResult(
                        model_name="changed_model",
                        change_kind=ChangeKind.QUERY_CHANGED,
                    ),
                    backfill=BackfillResult(action=BackfillAction.FULL),
                ),
                "backfill_model": ResolvedModelAction(
                    change=ChangeDetectionResult(
                        model_name="backfill_model",
                        change_kind=ChangeKind.NO_CHANGE,
                    ),
                    backfill=BackfillResult(action=BackfillAction.FULL),
                ),
            }
        ),
    )

    assert result.selected_keys == test_case.expected_selected_keys


@pytest.mark.parametrize(
    "test_case",
    [
        PruneUnchangedScopeTestCase(
            description="keeps unchanged model marked stale by source freshness",
            scope=PlannerScope(
                upstream_deps={},
                downstream_deps={},
                all_keys={},
                models_by_name={},
                selected_keys=frozenset({MODEL_UNCHANGED}),
                execution_order=(),
            ),
            expected_selected_keys=frozenset({MODEL_UNCHANGED}),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_stale_model_when_pruning_then_keeps_model(
    test_case: PruneUnchangedScopeTestCase,
) -> None:
    result: PlannerScope = prune_standard_unchanged_scope(
        scope=test_case.scope,
        changes=PlannerChangeResults(
            models={
                "unchanged_model": ChangeDetectionResult(
                    model_name="unchanged_model",
                    change_kind=ChangeKind.NO_CHANGE,
                ),
            },
            functions={},
        ),
        resolved_actions=PlannerResolvedActions(
            models={
                "unchanged_model": ResolvedModelAction(
                    change=ChangeDetectionResult(
                        model_name="unchanged_model",
                        change_kind=ChangeKind.NO_CHANGE,
                    ),
                    backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
                ),
            }
        ),
        source_freshness=StandardSourceFreshnessPlanningResult(
            propagation=StandardSourceFreshnessPropagationResult(
                stale_model_names=frozenset({"unchanged_model"}),
            ),
        ),
    )

    assert result.selected_keys == test_case.expected_selected_keys


@pytest.mark.parametrize(
    "test_case",
    [
        MarkVersionIdentityStaleActionsTestCase(
            description="composed version stale model does not add upstream cascade",
            model_key=MODEL_UNCHANGED,
            change_kind=ChangeKind.NO_CHANGE,
            previous_version_hash="old_version",
            expected_version_hash="new_version",
            expected_cascade_present=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_composed_version_stale_model_when_marking_actions_then_does_not_add_upstream_cascade(
    test_case: MarkVersionIdentityStaleActionsTestCase,
) -> None:
    scope: PlannerScope = PlannerScope(
        upstream_deps={},
        downstream_deps={},
        all_keys={},
        models_by_name={},
        selected_keys=frozenset({test_case.model_key}),
        execution_order=(),
    )
    resolved_actions: PlannerResolvedActions = PlannerResolvedActions(
        models={
            test_case.model_key.name: ResolvedModelAction(
                change=ChangeDetectionResult(
                    model_name=test_case.model_key.name,
                    change_kind=test_case.change_kind,
                    previous_version_hash=test_case.previous_version_hash,
                ),
                backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
            ),
        }
    )

    result: PlannerResolvedActions = mark_version_identity_stale_actions(
        scope=scope,
        resolved_actions=resolved_actions,
        expected_version_hashes={test_case.model_key.name: test_case.expected_version_hash},
    )

    marked_action: ResolvedModelAction = result.models[test_case.model_key.name]
    assert (marked_action.cascade is not None) == test_case.expected_cascade_present


@pytest.mark.parametrize(
    "test_case",
    [
        MarkVersionIdentityStaleActionsTestCase(
            description="locally changed model keeps existing reason",
            model_key=MODEL_CHANGED,
            change_kind=ChangeKind.QUERY_CHANGED,
            previous_version_hash="old_version",
            expected_version_hash="new_version",
            expected_cascade_present=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_locally_changed_model_when_marking_actions_then_keeps_existing_reason(
    test_case: MarkVersionIdentityStaleActionsTestCase,
) -> None:
    scope: PlannerScope = PlannerScope(
        upstream_deps={},
        downstream_deps={},
        all_keys={},
        models_by_name={},
        selected_keys=frozenset({test_case.model_key}),
        execution_order=(),
    )
    resolved_actions: PlannerResolvedActions = PlannerResolvedActions(
        models={
            test_case.model_key.name: ResolvedModelAction(
                change=ChangeDetectionResult(
                    model_name=test_case.model_key.name,
                    change_kind=test_case.change_kind,
                    previous_version_hash=test_case.previous_version_hash,
                ),
                backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
            ),
        }
    )

    result: PlannerResolvedActions = mark_version_identity_stale_actions(
        scope=scope,
        resolved_actions=resolved_actions,
        expected_version_hashes={test_case.model_key.name: test_case.expected_version_hash},
    )

    marked_action: ResolvedModelAction = result.models[test_case.model_key.name]
    assert (marked_action.cascade is not None) == test_case.expected_cascade_present


@pytest.mark.parametrize(
    "test_case",
    [
        DirectParentRunActionTestCase(
            description="direct model run marks child as upstream changed",
            parent_key=MODEL_CHANGED,
            child_key=MODEL_UNCHANGED,
            expected_cascade_present=True,
            expected_root_cause=MODEL_CHANGED.name,
            expected_root_reason=PlanReason.UPSTREAM_CHANGED,
        ),
        DirectParentRunActionTestCase(
            description="direct seed run marks child as upstream changed",
            parent_key=SEED_KEY,
            child_key=MODEL_UNCHANGED,
            expected_cascade_present=True,
            expected_root_cause=SEED_KEY.name,
            expected_root_reason=PlanReason.UPSTREAM_CHANGED,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_executable_direct_parent_run_scope_when_marking_then_child_gets_cascade(
    test_case: DirectParentRunActionTestCase,
) -> None:
    parent_key: CompiledObjectKey = test_case.parent_key
    child_key: CompiledObjectKey = test_case.child_key
    scope: PlannerScope = PlannerScope(
        upstream_deps={child_key: (parent_key,)},
        downstream_deps={parent_key: (child_key,)},
        all_keys={},
        models_by_name={},
        selected_keys=frozenset({parent_key, child_key}),
        execution_order=(),
    )
    resolved_actions: PlannerResolvedActions = PlannerResolvedActions(
        models={
            parent_key.name: ResolvedModelAction(
                change=ChangeDetectionResult(
                    model_name=parent_key.name,
                    change_kind=ChangeKind.QUERY_CHANGED,
                ),
                backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
            ),
            child_key.name: ResolvedModelAction(
                change=ChangeDetectionResult(
                    model_name=child_key.name,
                    change_kind=ChangeKind.NO_CHANGE,
                ),
                backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
            ),
        }
    )

    result: PlannerResolvedActions = mark_direct_parent_run_actions(
        scope=scope,
        resolved_actions=resolved_actions,
    )

    marked_action: ResolvedModelAction = result.models[child_key.name]
    assert marked_action.cascade is not None
    assert marked_action.cascade.root_cause == test_case.expected_root_cause
    assert marked_action.cascade.root_reason == test_case.expected_root_reason


@pytest.mark.parametrize(
    "test_case",
    [
        DirectParentRunActionTestCase(
            description="selected source parent does not mark child as upstream changed",
            parent_key=SOURCE_KEY,
            child_key=MODEL_UNCHANGED,
            expected_cascade_present=False,
        ),
        DirectParentRunActionTestCase(
            description="selected function parent does not mark child as upstream changed",
            parent_key=FUNCTION_CHANGED,
            child_key=MODEL_UNCHANGED,
            expected_cascade_present=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_executable_direct_parent_in_scope_when_marking_then_child_has_no_cascade(
    test_case: DirectParentRunActionTestCase,
) -> None:
    parent_key: CompiledObjectKey = test_case.parent_key
    child_key: CompiledObjectKey = test_case.child_key
    scope: PlannerScope = PlannerScope(
        upstream_deps={child_key: (parent_key,)},
        downstream_deps={parent_key: (child_key,)},
        all_keys={},
        models_by_name={},
        selected_keys=frozenset({parent_key, child_key}),
        execution_order=(),
    )
    resolved_actions: PlannerResolvedActions = PlannerResolvedActions(
        models={
            parent_key.name: ResolvedModelAction(
                change=ChangeDetectionResult(
                    model_name=parent_key.name,
                    change_kind=ChangeKind.QUERY_CHANGED,
                ),
                backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
            ),
            child_key.name: ResolvedModelAction(
                change=ChangeDetectionResult(
                    model_name=child_key.name,
                    change_kind=ChangeKind.NO_CHANGE,
                ),
                backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
            ),
        }
    )

    result: PlannerResolvedActions = mark_direct_parent_run_actions(
        scope=scope,
        resolved_actions=resolved_actions,
    )

    marked_action: ResolvedModelAction = result.models[child_key.name]
    assert (marked_action.cascade is not None) == test_case.expected_cascade_present
