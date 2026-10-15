"""Baseline comparison reports real plan differences, not where a captured type is defined."""

from __future__ import annotations

import pytest

from scripts.planner_differential._helpers.baseline.baseline import compare_documents
from tests.unit.scripts.planner_differential._helpers.baseline._test_types import (
    CompareDocumentsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CompareDocumentsTestCase(
            description="type_moved_to_native_module_matches",
            expected={
                "steps": [
                    {
                        "step": "plan",
                        "plan": {
                            "__type__": "sqlbuild.compiler.planner.models:PlanOutput",
                            "action": {
                                "__enum__": "sqlbuild.compiler.planner.types:PlanAction.CREATE"
                            },
                        },
                    }
                ]
            },
            actual={
                "steps": [
                    {
                        "step": "plan",
                        "plan": {
                            "__type__": "sqlbuild._native:PlanOutput",
                            "action": {"__enum__": "sqlbuild._native:PlanAction.CREATE"},
                        },
                    }
                ]
            },
            expected_artifacts=(),
        ),
        CompareDocumentsTestCase(
            description="different_type_or_member_still_differs",
            expected={
                "steps": [
                    {
                        "step": "plan",
                        "plan": {
                            "action": {
                                "__enum__": "sqlbuild.compiler.planner.types:PlanAction.CREATE"
                            }
                        },
                        "entry": {"__type__": "sqlbuild.compiler.planner.models:ModelPlanEntry"},
                    }
                ]
            },
            actual={
                "steps": [
                    {
                        "step": "plan",
                        "plan": {"action": {"__enum__": "sqlbuild._native:PlanAction.SKIP"}},
                        "entry": {"__type__": "sqlbuild._native:SeedPlanEntry"},
                    }
                ]
            },
            expected_artifacts=("plan", "entry"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_runs_when_comparing_then_reports_only_real_differences(
    test_case: CompareDocumentsTestCase,
) -> None:
    differences = compare_documents(expected=test_case.expected, actual=test_case.actual)

    assert tuple(difference.artifact for difference in differences) == test_case.expected_artifacts
