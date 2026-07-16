from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.changes.selection_staleness import (
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
MODEL_D: SelectionStalenessNodeKey = SelectionStalenessNodeKey(resource_type="model", name="d")
MODEL_E: SelectionStalenessNodeKey = SelectionStalenessNodeKey(resource_type="model", name="e")
MODEL_F: SelectionStalenessNodeKey = SelectionStalenessNodeKey(resource_type="model", name="f")
SEED_ORDERS: SelectionStalenessNodeKey = SelectionStalenessNodeKey(
    resource_type="seed", name="raw_orders"
)
SEED_CUSTOMERS: SelectionStalenessNodeKey = SelectionStalenessNodeKey(
    resource_type="seed", name="raw_customers"
)
SOURCE_ORDERS: SelectionStalenessNodeKey = SelectionStalenessNodeKey(
    resource_type="source", name="raw_orders"
)
SOURCE_CUSTOMERS: SelectionStalenessNodeKey = SelectionStalenessNodeKey(
    resource_type="source", name="raw_customers"
)
FUNCTION_F: SelectionStalenessNodeKey = SelectionStalenessNodeKey(
    resource_type="function", name="fn_normalize"
)


@pytest.mark.parametrize(
    "test_case",
    [
        SelectionStalenessClassifierTestCase(
            description="direct changed model parent outside selection warns",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"b"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(SelectionStalenessWarning(model_name="c", trigger_names=("b",)),),
        ),
        SelectionStalenessClassifierTestCase(
            description="direct changed model parent in run set does not warn",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,)},
                selected_model_names=frozenset({"b", "c"}),
                run_model_names=frozenset({"b", "c"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"b"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(),
        ),
        SelectionStalenessClassifierTestCase(
            description="direct unchanged parent outside selection does not warn",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset(),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(),
        ),
        SelectionStalenessClassifierTestCase(
            description="multi-hop changed model root outside selection reports root and intermediate",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (MODEL_A,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("a", "b")),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="selected root and leaf warns for unbuilt intermediate",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (MODEL_A,)},
                selected_model_names=frozenset({"a", "c"}),
                run_model_names=frozenset({"a"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(SelectionStalenessWarning(model_name="c", trigger_names=("b",)),),
        ),
        SelectionStalenessClassifierTestCase(
            description="multi-hop full selected run closure does not warn",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (MODEL_A,)},
                selected_model_names=frozenset({"a", "b", "c"}),
                run_model_names=frozenset({"a", "b", "c"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(),
        ),
        SelectionStalenessClassifierTestCase(
            description="selected intermediate and leaf still warn for unselected changed root",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (MODEL_A,)},
                selected_model_names=frozenset({"b", "c"}),
                run_model_names=frozenset({"b", "c"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="b", trigger_names=("a",)),
                SelectionStalenessWarning(model_name="c", trigger_names=("a",)),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="branching changed model roots outside selection warn deterministically",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_E: (MODEL_B, MODEL_D), MODEL_B: (MODEL_A,)},
                selected_model_names=frozenset({"e"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a", "d"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="e", trigger_names=("a", "b", "d")),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="mixed selected and unselected changed parents runs and warns",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_A, MODEL_B)},
                selected_model_names=frozenset({"b", "c"}),
                run_model_names=frozenset({"b", "c"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a", "b"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(SelectionStalenessWarning(model_name="c", trigger_names=("a",)),),
        ),
        SelectionStalenessClassifierTestCase(
            description="mixed multi-hop branches ignore rebuilt branch and warn for stale branch",
            graph=SelectionStalenessGraph(
                upstream_deps={
                    MODEL_E: (MODEL_B, MODEL_D),
                    MODEL_B: (MODEL_A,),
                    MODEL_D: (MODEL_C,),
                },
                selected_model_names=frozenset({"a", "b", "e"}),
                run_model_names=frozenset({"a", "b", "e"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a", "c"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="e", trigger_names=("c", "d")),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="diamond changed root reports both stale intermediates",
            graph=SelectionStalenessGraph(
                upstream_deps={
                    MODEL_D: (MODEL_B, MODEL_C),
                    MODEL_B: (MODEL_A,),
                    MODEL_C: (MODEL_A,),
                },
                selected_model_names=frozenset({"d"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="d", trigger_names=("a", "b", "c")),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="direct changed seed outside selection warns",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (SEED_ORDERS,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset(),
                changed_seed_names=frozenset({"raw_orders"}),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("raw_orders",)),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="direct changed seed in run set does not warn",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (SEED_ORDERS,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset({"c"}),
                run_seed_names=frozenset({"raw_orders"}),
                run_source_names=frozenset(),
                changed_model_names=frozenset(),
                changed_seed_names=frozenset({"raw_orders"}),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(),
        ),
        SelectionStalenessClassifierTestCase(
            description="multi-hop changed seed root reports seed and stale intermediate",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (SEED_ORDERS,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset(),
                changed_seed_names=frozenset({"raw_orders"}),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("b", "raw_orders")),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="changed seed and leaf own change runs and still warns",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (SEED_ORDERS,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset({"c"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"c"}),
                changed_seed_names=frozenset({"raw_orders"}),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("b", "raw_orders")),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="two seed roots warn only for unselected changed seed",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (SEED_ORDERS, SEED_CUSTOMERS)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset({"c"}),
                run_seed_names=frozenset({"raw_orders"}),
                run_source_names=frozenset(),
                changed_model_names=frozenset(),
                changed_seed_names=frozenset({"raw_orders", "raw_customers"}),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("raw_customers",)),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="direct changed source outside selection warns",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (SOURCE_ORDERS,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset(),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset({"raw_orders"}),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("raw_orders",)),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="direct changed source in run set does not warn",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (SOURCE_ORDERS,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset({"c"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset({"raw_orders"}),
                changed_model_names=frozenset(),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset({"raw_orders"}),
            ),
            expected_warnings=(),
        ),
        SelectionStalenessClassifierTestCase(
            description="multi-hop changed source root reports source and stale intermediate",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,), MODEL_B: (SOURCE_ORDERS,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset(),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset({"raw_orders"}),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("b", "raw_orders")),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="selected leaf full refresh equivalent run still warns for changed upstream",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset({"c"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"b"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(SelectionStalenessWarning(model_name="c", trigger_names=("b",)),),
        ),
        SelectionStalenessClassifierTestCase(
            description="selected leaf run warns only for unselected source",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B, SOURCE_ORDERS)},
                selected_model_names=frozenset({"b", "c"}),
                run_model_names=frozenset({"b", "c"}),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"b"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset({"raw_orders"}),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("raw_orders",)),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="changed function parent is ignored by neutral classifier",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (FUNCTION_F,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"fn_normalize"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(),
        ),
        SelectionStalenessClassifierTestCase(
            description="unrelated changed model does not warn selected model",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_B,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"d"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(),
        ),
        SelectionStalenessClassifierTestCase(
            description="changed downstream does not warn selected upstream",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_D: (MODEL_C,)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"d"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(),
        ),
        SelectionStalenessClassifierTestCase(
            description="multiple selected models each report their own stale upstreams",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_A,), MODEL_D: (MODEL_B,)},
                selected_model_names=frozenset({"c", "d"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a", "b"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("a",)),
                SelectionStalenessWarning(model_name="d", trigger_names=("b",)),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="cycle terminates and reports changed root and stale intermediate",
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
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("a", "b")),
            ),
        ),
        SelectionStalenessClassifierTestCase(
            description="self cycle terminates and still reports independent changed parent",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_C, MODEL_A)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(SelectionStalenessWarning(model_name="c", trigger_names=("a",)),),
        ),
        SelectionStalenessClassifierTestCase(
            description="all stale roots are returned for formatter-level capping",
            graph=SelectionStalenessGraph(
                upstream_deps={MODEL_C: (MODEL_A, MODEL_B, MODEL_D, MODEL_E, MODEL_F)},
                selected_model_names=frozenset({"c"}),
                run_model_names=frozenset(),
                run_seed_names=frozenset(),
                run_source_names=frozenset(),
                changed_model_names=frozenset({"a", "b", "d", "e", "f"}),
                changed_seed_names=frozenset(),
                changed_source_names=frozenset(),
            ),
            expected_warnings=(
                SelectionStalenessWarning(model_name="c", trigger_names=("a", "b", "d", "e", "f")),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_graph_when_classifying_then_reports_expected_warnings(
    test_case: SelectionStalenessClassifierTestCase,
) -> None:
    warnings: tuple[SelectionStalenessWarning, ...] = classify_selection_staleness_warnings(
        test_case.graph
    )

    assert warnings == test_case.expected_warnings
