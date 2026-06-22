from __future__ import annotations

from typing import ClassVar

import pytest

from sqlbuild.compiler.compile.models.core import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.helpers.scenario.cli import build_cli_scenario_plan
from sqlbuild.compiler.planner.models import ScenarioArtifactName, ScenarioExecutionPlan
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    ScenarioCliPlanIdentifierLimitTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    PlannerTestAdapter,
    build_scenario_cli_identifier_limit_pipeline,
)


class WideIdentifierPlannerTestAdapter(PlannerTestAdapter):
    max_identifier_length: ClassVar[int] = 255


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCliPlanIdentifierLimitTestCase(
            description="uses adapter identifier limit for scenario artifact names",
            model_name="very_long_customer_revenue_reconciliation_by_region_and_day",
            expected_model_physical_name=(
                "__sqb_01483982d3b6__model__"
                "very_long_customer_revenue_reconciliation_by_region_and_day"
            ),
        )
    ],
    ids=["uses adapter identifier limit for scenario artifact names"],
)
def test_given_adapter_identifier_limit_when_building_cli_scenario_plan_then_uses_adapter_limit(
    test_case: ScenarioCliPlanIdentifierLimitTestCase,
) -> None:
    scenario: CompiledSqlScenario
    pipeline_result: CompilePipelineResult
    scenario, pipeline_result = build_scenario_cli_identifier_limit_pipeline(
        model_name=test_case.model_name
    )

    result: ScenarioExecutionPlan = build_cli_scenario_plan(
        scenario=scenario,
        pipeline_result=pipeline_result,
        adapter=WideIdentifierPlannerTestAdapter(),
        project_name="scenario_demo",
    )

    model_artifacts: tuple[ScenarioArtifactName, ...] = tuple(
        artifact
        for artifact in result.relation_plan.relation_map.artifacts
        if artifact.identity.kind == "model"
    )
    assert len(model_artifacts) == 1
    assert model_artifacts[0].physical_name == test_case.expected_model_physical_name
