from __future__ import annotations

from typing import Any, cast

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.changes_only import (
    build_standard_identity_stale_model_names,
    mark_version_identity_stale_actions,
    prune_unchanged_scope,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeResult,
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
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    DirectIdentityStaleModelNamesTestCase,
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
    resource_type=CompiledResourceType.FUNCTION,
    name="unchanged_function",
)
FUNCTION_CHANGED: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.FUNCTION,
    name="changed_function",
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
    ids=["returns models with missing or mismatched built identities"],
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
    ids=["keeps stale SQL keys and non-model resources"],
)
def test_given_mixed_change_results_when_pruning_unchanged_scope_then_keeps_only_stale_sql_keys(
    test_case: PruneUnchangedScopeTestCase,
) -> None:
    result: PlannerScope = prune_unchanged_scope(
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
    ids=["keeps unchanged model marked stale by source freshness"],
)
def test_given_source_freshness_stale_model_when_pruning_then_keeps_model(
    test_case: PruneUnchangedScopeTestCase,
) -> None:
    result: PlannerScope = prune_unchanged_scope(
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
            description="composed version stale model adds upstream cascade",
            model_key=MODEL_UNCHANGED,
            change_kind=ChangeKind.NO_CHANGE,
            previous_version_hash="old_version",
            expected_version_hash="new_version",
            expected_cascade_present=True,
        )
    ],
    ids=["composed version stale model adds upstream cascade"],
)
def test_given_composed_version_stale_model_when_marking_actions_then_adds_upstream_cascade(
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
    assert marked_action.cascade is not None
    cascade: CascadeResult = marked_action.cascade
    assert cascade.effective_action == BackfillAction.FORWARD_ONLY
    assert cascade.effective_duration is None


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
    ids=["locally changed model keeps existing reason"],
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
