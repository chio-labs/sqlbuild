from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.selection_staleness import (
    classify_selection_staleness_warnings,
)
from sqlbuild.compiler.planner.models import (
    SelectionStalenessGraph,
    SelectionStalenessNodeKey,
    SelectionStalenessWarning,
)
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    SelectionStalenessClassifierTestCase,
)

MODEL_A: SelectionStalenessNodeKey = SelectionStalenessNodeKey(resource_type="model", name="a")
MODEL_B: SelectionStalenessNodeKey = SelectionStalenessNodeKey(resource_type="model", name="b")
MODEL_C: SelectionStalenessNodeKey = SelectionStalenessNodeKey(resource_type="model", name="c")
SEED_A: SelectionStalenessNodeKey = SelectionStalenessNodeKey(resource_type="seed", name="a")
SOURCE_D: SelectionStalenessNodeKey = SelectionStalenessNodeKey(resource_type="source", name="d")

TEST_CASES: list[SelectionStalenessClassifierTestCase] = [
    SelectionStalenessClassifierTestCase(
        description="branching changed roots reports stale triggers",
        graph=SelectionStalenessGraph(
            upstream_deps={MODEL_C: (MODEL_B, SOURCE_D), MODEL_B: (SEED_A,)},
            selected_model_names=frozenset({"c"}),
            run_model_names=frozenset(),
            run_seed_names=frozenset(),
            run_source_names=frozenset(),
            changed_model_names=frozenset(),
            changed_seed_names=frozenset({"a"}),
            changed_source_names=frozenset({"d"}),
        ),
        expected_warnings=(
            SelectionStalenessWarning(model_name="c", trigger_names=("a", "b", "d")),
        ),
    ),
    SelectionStalenessClassifierTestCase(
        description="cycle terminates and reports changed root",
        graph=SelectionStalenessGraph(
            upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (MODEL_A,), MODEL_A: (MODEL_B,)},
            selected_model_names=frozenset({"c"}),
            run_model_names=frozenset(),
            run_seed_names=frozenset(),
            run_source_names=frozenset(),
            changed_model_names=frozenset({"a"}),
            changed_seed_names=frozenset(),
            changed_source_names=frozenset(),
        ),
        expected_warnings=(SelectionStalenessWarning(model_name="c", trigger_names=("a", "b")),),
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_graph_when_classifying_then_reports_expected_warnings(
    test_case: SelectionStalenessClassifierTestCase,
) -> None:
    warnings: tuple[SelectionStalenessWarning, ...] = classify_selection_staleness_warnings(
        test_case.graph
    )

    assert warnings == test_case.expected_warnings
