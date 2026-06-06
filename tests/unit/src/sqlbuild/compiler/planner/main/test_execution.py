from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.main.execution import build_execution_plan
from sqlbuild.compiler.planner.models import PlanOutput
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    DirectSourceFreshnessPlanOutputTestCase,
    HookFunctionPlanOutputTestCase,
)

PLAN_OUTPUT_TEST_CASES: list[DirectSourceFreshnessPlanOutputTestCase] = [
    DirectSourceFreshnessPlanOutputTestCase(
        description="direct changes-only plan output carries source freshness result",
        changes_only=True,
        expected_has_source_freshness=True,
    ),
    DirectSourceFreshnessPlanOutputTestCase(
        description="normal direct plan output omits source freshness result",
        changes_only=False,
        expected_has_source_freshness=False,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLAN_OUTPUT_TEST_CASES,
    ids=[case.description for case in PLAN_OUTPUT_TEST_CASES],
)
def test_given_direct_plan_when_building_execution_plan_then_source_freshness_matches_changes_only(
    test_case: DirectSourceFreshnessPlanOutputTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        plan_output: PlanOutput = build_execution_plan(
            project=CompiledProject(
                run_id="test_run",
                effective_target_name=None,
                effective_connection={},
                effective_vars={},
            ),
            adapter=adapter,
            connection=connection,
            changes_only=test_case.changes_only,
        )
    finally:
        adapter.close(connection)

    assert (plan_output.source_freshness is not None) == test_case.expected_has_source_freshness


@pytest.mark.parametrize(
    "test_case",
    [
        HookFunctionPlanOutputTestCase(
            description="execution plan carries discovered hook functions",
            expected_hook_names=("notify",),
        )
    ],
    ids=["execution plan carries discovered hook functions"],
)
def test_given_project_with_hook_functions_when_building_execution_plan_then_plan_carries_hooks(
    test_case: HookFunctionPlanOutputTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})

    def notify() -> None:
        return None

    try:
        plan_output: PlanOutput = build_execution_plan(
            project=CompiledProject(
                run_id="test_run",
                effective_target_name=None,
                effective_connection={},
                effective_vars={},
                hook_functions=(
                    DiscoveredHookFunction(
                        file_path=Path(__file__),
                        relative_path=Path("hooks/notify.py"),
                        name="notify",
                        function=notify,
                    ),
                ),
            ),
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert tuple(hook.name for hook in plan_output.hook_functions) == test_case.expected_hook_names
