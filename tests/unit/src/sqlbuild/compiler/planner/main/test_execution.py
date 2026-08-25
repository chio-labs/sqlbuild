from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    PlanOutput,
)
from sqlbuild.compiler.planner.types import (
    PlanAction,
    PlanReason,
)
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    DirectSourceFreshnessPlanOutputTestCase,
    ExternalBlockedPlanOutputTestCase,
    HookFunctionPlanOutputTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.main.helpers import (
    build_execution_plan_from_kwargs,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import build_compiled_project_with_models


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceFreshnessPlanOutputTestCase(
            description="direct plan output carries source freshness result",
            expected_has_source_freshness=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_direct_plan_when_building_execution_plan_then_source_freshness_is_available(
    test_case: DirectSourceFreshnessPlanOutputTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        plan_output: PlanOutput = build_execution_plan_from_kwargs(
            project=CompiledProject(
                run_id="test_run",
                effective_target_name=None,
                effective_connection={},
                effective_vars={},
            ),
            adapter=adapter,
            connection=connection,
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
    ids=lambda case: case.description,
)
def test_given_project_with_hook_functions_when_building_execution_plan_then_plan_carries_hooks(
    test_case: HookFunctionPlanOutputTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})

    def notify() -> None:
        return None

    try:
        plan_output: PlanOutput = build_execution_plan_from_kwargs(
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


@pytest.mark.parametrize(
    "test_case",
    [
        ExternalBlockedPlanOutputTestCase(
            description="external blocked overlay skips blocked model but keeps sibling work",
            expected_model_names=("blocked", "unrelated"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_external_blocked_model_when_building_execution_plan_then_only_that_model_is_skipped(
    test_case: ExternalBlockedPlanOutputTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    project: CompiledProject = build_compiled_project_with_models(
        {
            "blocked": "select 1 as id",
            "unrelated": "select 2 as id",
        }
    )
    try:
        plan_output: PlanOutput = build_execution_plan_from_kwargs(
            project=project,
            adapter=adapter,
            connection=connection,
            select=("blocked", "unrelated"),
            external_blocked_model_names=("blocked",),
        )
    finally:
        adapter.close(connection)

    entries_by_name: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in plan_output.model_entries
    }
    assert tuple(sorted(entries_by_name)) == test_case.expected_model_names
    assert entries_by_name["blocked"].action == PlanAction.SKIP
    assert entries_by_name["blocked"].reason == PlanReason.EXTERNAL_UPSTREAM_FAILED
    assert entries_by_name["unrelated"].action != PlanAction.SKIP
