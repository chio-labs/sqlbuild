from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.graph_changes_only import (
    build_graph_changes_only_propagation,
)
from sqlbuild.compiler.planner.models import (
    GraphChangesOnlyPropagationInput,
    GraphChangesOnlyPropagationResult,
    GraphNodeKey,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    GraphChangesOnlyPropagationTestCase,
)

SOURCE: GraphNodeKey = GraphNodeKey(node_type="dbt", node_name="source.analytics.raw.orders")
SEED: GraphNodeKey = GraphNodeKey(node_type="dbt", node_name="seed.analytics.raw_orders")
ROOT: GraphNodeKey = GraphNodeKey(node_type="dbt", node_name="model.analytics.stg_orders")
CHILD: GraphNodeKey = GraphNodeKey(node_type="dbt", node_name="model.analytics.fact_orders")
LEAF: GraphNodeKey = GraphNodeKey(node_type="dbt", node_name="model.analytics.downstream_orders")

TEST_CASES: list[GraphChangesOnlyPropagationTestCase] = [
    GraphChangesOnlyPropagationTestCase(
        description="blocks model when transitive source is blocked",
        upstream_deps={ROOT: (SOURCE,), CHILD: (ROOT,), LEAF: (CHILD,)},
        model_keys=frozenset({ROOT, CHILD, LEAF}),
        selected_model_keys=frozenset({LEAF}),
        current_model_keys=frozenset({ROOT, CHILD, LEAF}),
        run_model_keys=frozenset(),
        version_mismatch_model_keys=frozenset(),
        blocked_source_keys=frozenset({SOURCE}),
        expected_result=GraphChangesOnlyPropagationResult(
            blocked_model_keys=frozenset({ROOT, CHILD, LEAF}),
            blocked_source_keys_by_model_key={
                ROOT: (SOURCE,),
                CHILD: (SOURCE,),
                LEAF: (SOURCE,),
            },
        ),
    ),
    GraphChangesOnlyPropagationTestCase(
        description="propagates selected direct upstream run to selected child only",
        upstream_deps={ROOT: (SEED,), CHILD: (ROOT,), LEAF: (CHILD,)},
        model_keys=frozenset({ROOT, CHILD, LEAF}),
        selected_model_keys=frozenset({ROOT, CHILD}),
        current_model_keys=frozenset({CHILD, LEAF}),
        run_model_keys=frozenset({ROOT}),
        version_mismatch_model_keys=frozenset({CHILD, LEAF}),
        expected_result=GraphChangesOnlyPropagationResult(
            upstream_changed_model_keys=frozenset({CHILD})
        ),
    ),
    GraphChangesOnlyPropagationTestCase(
        description="marks current model stale when selected seed changed",
        upstream_deps={ROOT: (SEED,), CHILD: (ROOT,)},
        model_keys=frozenset({ROOT, CHILD}),
        selected_model_keys=frozenset({ROOT}),
        current_model_keys=frozenset({ROOT, CHILD}),
        run_model_keys=frozenset(),
        version_mismatch_model_keys=frozenset(),
        changed_seed_keys=frozenset({SEED}),
        expected_result=GraphChangesOnlyPropagationResult(
            seed_changed_model_keys=frozenset({ROOT, CHILD})
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_changes_only_graph_when_propagating_then_returns_expected_result(
    test_case: GraphChangesOnlyPropagationTestCase,
) -> None:
    result: GraphChangesOnlyPropagationResult = build_graph_changes_only_propagation(
        request=GraphChangesOnlyPropagationInput(
            upstream_deps=dict(test_case.upstream_deps),
            model_keys=test_case.model_keys,
            selected_model_keys=test_case.selected_model_keys,
            current_model_keys=test_case.current_model_keys,
            run_model_keys=test_case.run_model_keys,
            version_mismatch_model_keys=test_case.version_mismatch_model_keys,
            changed_seed_keys=test_case.changed_seed_keys,
            changed_source_keys=test_case.changed_source_keys,
            blocked_source_keys=test_case.blocked_source_keys,
        )
    )

    assert result == test_case.expected_result
