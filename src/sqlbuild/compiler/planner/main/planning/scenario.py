"""Public scenario planner entry point."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner._helpers.scenario.cli import build_cli_scenario_plan
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan


def build_scenario_plan(
    *,
    scenario: CompiledSqlScenario,
    pipeline_result: CompilePipelineResult,
    adapter: BaseAdapter,
    project_name: str,
) -> ScenarioExecutionPlan:
    """Build a scenario execution plan for an external entrypoint."""

    return build_cli_scenario_plan(
        scenario=scenario,
        pipeline_result=pipeline_result,
        adapter=adapter,
        project_name=project_name,
    )
