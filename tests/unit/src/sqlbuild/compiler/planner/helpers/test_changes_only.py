from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.changes_only import prune_unchanged_scope
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
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
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
                    backfill=BackfillResult(action=BackfillAction.WARN_ONLY),
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
