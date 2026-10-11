from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.compiled_project._test_types import (
    HandBuiltAnalysisTestCase,
)
from tests.integration.src.sqlbuild.compiler.compiled_project.helpers import (
    hand_built_analysed_project,
    model_analysis_summary,
    native_analysed_project,
)

_ORDERS: str = "SELECT 1 AS order_id, 2 AS amount"


@pytest.mark.parametrize(
    "test_case",
    [
        HandBuiltAnalysisTestCase(
            description="a typo locates its binding error in the authored file",
            models={
                "orders": _ORDERS,
                "report": 'SELECT o.order_id, o.missing\nFROM __ref("orders") AS o',
            },
            expected_models=(
                ("orders", ("order_id", "amount"), ("order_id", "amount"), False, True, ()),
                (
                    "report",
                    ("order_id", "missing"),
                    ("order_id", "missing"),
                    False,
                    True,
                    (("B002", 3, 22, 29),),
                ),
            ),
        ),
        HandBuiltAnalysisTestCase(
            description="a clean star model keeps native columns and lineage",
            models={"orders": _ORDERS, "report": 'SELECT *\nFROM __ref("orders")'},
            expected_models=(
                ("orders", ("order_id", "amount"), ("order_id", "amount"), False, True, ()),
                ("report", ("order_id", "amount"), ("order_id", "amount"), True, True, ()),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_models_when_assembling_natively_and_hand_built_then_analysis_facts_match(
    test_case: HandBuiltAnalysisTestCase, tmp_path: Path
) -> None:
    native: tuple[tuple[object, ...], ...] = model_analysis_summary(
        native_analysed_project(project_dir=tmp_path, models=test_case.models)
    )
    hand_built: tuple[tuple[object, ...], ...] = model_analysis_summary(
        hand_built_analysed_project(test_case.models)
    )

    assert (native, hand_built) == (test_case.expected_models, test_case.expected_models)
