from __future__ import annotations

import pytest

from sqlbuild.compiler.pipeline.main.operations.plan_work import plan_has_executable_work
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.types import (
    PythonIdentityStatus,
    PythonNodeKind,
    PythonRunPhase,
)
from tests.unit.src.sqlbuild.compiler.pipeline.main._test_types import PlanWorkTestCase
from tests.unit.src.sqlbuild.compiler.pipeline.main.helpers import build_plan_output_with_model

TEST_CASES: list[PlanWorkTestCase] = [
    PlanWorkTestCase(
        description="empty plan has no executable work",
        plan_output=PlanOutput(),
        python_plan_entries=(),
        expected_has_work=False,
    ),
    PlanWorkTestCase(
        description="pruned metadata alone has no executable work",
        plan_output=PlanOutput(metadata={"standard_pruned_model_names": ("orders",)}),
        python_plan_entries=(),
        expected_has_work=False,
    ),
    PlanWorkTestCase(
        description="model entry has executable work",
        plan_output=build_plan_output_with_model(),
        python_plan_entries=(),
        expected_has_work=True,
    ),
    PlanWorkTestCase(
        description="python entry has executable work",
        plan_output=PlanOutput(),
        python_plan_entries=(
            PythonPlanEntry(
                name="export_orders",
                kind=PythonNodeKind.ASSET,
                phase=PythonRunPhase.READ_SIDE,
                identity_status=PythonIdentityStatus.CHANGED,
            ),
        ),
        expected_has_work=True,
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_plan_work_inputs_when_checking_executable_work_then_returns_expected_result(
    test_case: PlanWorkTestCase,
) -> None:
    result: bool = plan_has_executable_work(
        test_case.plan_output, python_plan_entries=test_case.python_plan_entries
    )

    assert result is test_case.expected_has_work
