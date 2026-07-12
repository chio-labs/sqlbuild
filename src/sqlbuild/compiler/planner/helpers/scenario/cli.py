"""CLI-facing scenario planning helper."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledSqlScenario,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.scenario.artifacts import (
    build_scenario_hash_index,
    build_scenario_relation_map,
)
from sqlbuild.compiler.planner.helpers.scenario.graph import plan_scenario_graph
from sqlbuild.compiler.planner.helpers.scenario.relations import (
    build_scenario_execution_plan,
    build_scenario_relation_plan,
)
from sqlbuild.compiler.planner.models import (
    PlanWarning,
    ScenarioArtifactIdentity,
    ScenarioExecutionPlan,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
)
from sqlbuild.compiler.planner.types import ScenarioArtifactKind, WarningSeverity
from sqlbuild.shared.constants import SCENARIO_PLAN_GRAPH_VALIDATION


def build_cli_scenario_plan(
    *,
    scenario: CompiledSqlScenario,
    pipeline_result: CompilePipelineResult,
    adapter: BaseAdapter,
    project_name: str,
) -> ScenarioExecutionPlan:
    """Build a scenario execution plan for CLI execution."""

    graph_plan: ScenarioGraphPlan
    graph_warnings: tuple[PlanWarning, ...]
    graph_plan, graph_warnings = plan_scenario_graph(
        scenario=scenario,
        project=pipeline_result.project,
    )
    _raise_for_error_warnings(graph_warnings)
    hash_index: dict[str, str] = build_scenario_hash_index(
        project_name=project_name,
        scenarios=pipeline_result.project.sql_scenarios,
    )
    relation_map: ScenarioRelationMap = build_scenario_relation_map(
        scenario_name=scenario.name,
        hash_prefix=hash_index[scenario.name],
        artifacts=_scenario_artifacts(graph_plan),
        identifier_limit=adapter.maximum_identifier_length(),
    )
    database: str | None
    schema: str | None
    database, schema = _scenario_namespace(project=pipeline_result.project, graph_plan=graph_plan)
    relation_plan: ScenarioRelationPlan = build_scenario_relation_plan(
        project=pipeline_result.project,
        graph_plan=graph_plan,
        relation_map=relation_map,
        render_qualified_name=adapter.render_qualified_name,
        database=database,
        schema=schema,
    )
    scenario_plan: ScenarioExecutionPlan
    execution_warnings: tuple[PlanWarning, ...]
    scenario_plan, execution_warnings = build_scenario_execution_plan(
        scenario=scenario,
        project=pipeline_result.project,
        adapter=adapter,
        graph_plan=graph_plan,
        relation_plan=relation_plan,
    )
    _raise_for_error_warnings(execution_warnings)
    return scenario_plan


def _scenario_artifacts(graph_plan: ScenarioGraphPlan) -> tuple[ScenarioArtifactIdentity, ...]:
    artifacts: list[ScenarioArtifactIdentity] = []
    source_name: str
    for source_name in graph_plan.source_fixture_names:
        artifacts.append(
            ScenarioArtifactIdentity(kind=ScenarioArtifactKind.SOURCE, logical_name=source_name)
        )
    ref_name: str
    for ref_name in graph_plan.ref_fixture_names:
        artifacts.append(
            ScenarioArtifactIdentity(kind=ScenarioArtifactKind.REF, logical_name=ref_name)
        )
    dbt_ref_name: str
    for dbt_ref_name in graph_plan.dbt_ref_fixture_names:
        artifacts.append(
            ScenarioArtifactIdentity(kind=ScenarioArtifactKind.DBT_REF, logical_name=dbt_ref_name)
        )
    seed_name: str
    for seed_name in graph_plan.seed_names:
        artifacts.append(
            ScenarioArtifactIdentity(kind=ScenarioArtifactKind.SEED, logical_name=seed_name)
        )
    model_name: str
    for model_name in graph_plan.model_names:
        artifacts.append(
            ScenarioArtifactIdentity(kind=ScenarioArtifactKind.MODEL, logical_name=model_name)
        )
    return tuple(artifacts)


def _scenario_namespace(
    *, project: CompiledProject, graph_plan: ScenarioGraphPlan
) -> tuple[str | None, str | None]:
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    model_name: str
    for model_name in (*graph_plan.target_model_names, *graph_plan.model_names):
        model: CompiledModel | None = models_by_name.get(model_name)
        if model is not None:
            return model.destination.database, model.destination.schema
    return None, None


def _raise_for_error_warnings(warnings: tuple[PlanWarning, ...]) -> None:
    error_warnings: tuple[PlanWarning, ...] = tuple(
        warning for warning in warnings if warning.severity == WarningSeverity.ERROR
    )
    if error_warnings:
        raise PlannerInputError(
            "\n".join(warning.message for warning in error_warnings),
            code=error_warnings[0].code or SCENARIO_PLAN_GRAPH_VALIDATION,
        )
