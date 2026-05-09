"""Helpers for executor pipeline helper tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompiledSqlScenario
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import (
    PlanOutput,
    ScenarioExecutionPlan,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
)


class ScenarioPipelineTestAdapter(BaseAdapter):
    """Adapter that records pipeline connection lifecycle calls."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        database: object = config.get("database", "")
        self.events.append(f"connect:{database}")
        return object()

    def execute(self, connection: object, sql: str) -> object:
        del connection, sql
        return object()

    def close(self, connection: object) -> None:
        del connection
        self.events.append("close")


class ScenarioPipelinePlanBuilder:
    """Callable plan builder that can fail for one configured scenario."""

    def __init__(self, *, planning_failure_name: str, error_message: str) -> None:
        self.planning_failure_name: str = planning_failure_name
        self.error_message: str = error_message

    def __call__(
        self,
        *,
        scenario: CompiledSqlScenario,
        pipeline_result: CompilePipelineResult,
        adapter: ScenarioPipelineTestAdapter,
        project_name: str,
    ) -> ScenarioExecutionPlan:
        del pipeline_result, adapter, project_name
        if scenario.name == self.planning_failure_name:
            raise RuntimeError(self.error_message)
        return build_scenario_pipeline_plan(scenario=scenario)


def build_scenario_pipeline_result(*, scenario_names: tuple[str, ...]) -> CompilePipelineResult:
    """Build a minimal compile pipeline result containing SQL scenarios."""

    scenarios: tuple[CompiledSqlScenario, ...] = tuple(
        build_compiled_scenario(name=name) for name in scenario_names
    )
    return CompilePipelineResult(
        project=CompiledProject(
            run_id="scenario-test-run",
            effective_environment_name=None,
            effective_connection={},
            effective_vars={},
            sql_scenarios=scenarios,
        ),
        plan_output=PlanOutput(),
    )


def build_compiled_scenario(*, name: str) -> CompiledSqlScenario:
    """Build a minimal compiled SQL scenario for pipeline tests."""

    return CompiledSqlScenario(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_SCENARIO,
            name=name,
        ),
        name=name,
        scenario_file=DiscoveredSqlScenarioFile(
            file_path=Path(f"tests/scenarios/{name}.sql"),
            relative_path=Path(f"tests/scenarios/{name}.sql"),
            contents="SCENARIO ();",
            header_values={},
            sql_body="",
            name=name,
        ),
        sql_body="",
    )


def build_scenario_pipeline_plan(*, scenario: CompiledSqlScenario) -> ScenarioExecutionPlan:
    """Build a minimal scenario execution plan for pipeline tests."""

    return ScenarioExecutionPlan(
        key=scenario.key,
        name=scenario.name,
        graph_plan=ScenarioGraphPlan(key=scenario.key, name=scenario.name),
        relation_plan=ScenarioRelationPlan(
            scenario_name=scenario.name,
            relation_map=ScenarioRelationMap(
                scenario_name=scenario.name,
                hash_prefix="51b385aebe20",
            ),
        ),
    )
