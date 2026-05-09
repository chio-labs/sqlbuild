from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    ScenarioExecutionPlan,
    ScenarioFixturePlan,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
)
from sqlbuild.compiler.planner.types import ScenarioArtifactKind


class ScenarioFixtureTestAdapter(BaseAdapter):
    """Adapter that records scenario fixture materialization calls."""

    def __init__(self, *, fail_on_target: str | None = None) -> None:
        self.fail_on_target: str | None = fail_on_target
        self.executed_sql: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def execute(self, connection: object, sql: str) -> object:
        del connection
        self.executed_sql.append(sql)
        if self.fail_on_target is not None and self.fail_on_target in sql:
            raise RuntimeError(f"failed target {self.fail_on_target}")
        return object()

    def close(self, connection: object) -> None:
        del connection


def build_scenario_fixture_plan(
    *,
    kind: ScenarioArtifactKind = ScenarioArtifactKind.SOURCE,
    logical_name: str = "raw__orders",
    target_name: str = "__sqb_51b385aebe20__source__raw__orders",
    sql: str = "WITH helper_orders AS (SELECT 1 AS order_id) SELECT * FROM helper_orders",
) -> ScenarioFixturePlan:
    return ScenarioFixturePlan(
        kind=kind,
        logical_name=logical_name,
        target=CompiledRelationTarget(
            database=None,
            schema="scenario_schema",
            name=target_name,
            qualified_name=f"scenario_schema.{target_name}",
        ),
        sql=sql,
    )


def executed_create_table_sql(adapter: ScenarioFixtureTestAdapter) -> tuple[str, ...]:
    return tuple(sql for sql in adapter.executed_sql if "CREATE OR REPLACE TABLE" in sql)


def executed_drop_sql(adapter: ScenarioFixtureTestAdapter) -> tuple[str, ...]:
    return tuple(sql for sql in adapter.executed_sql if sql.startswith("DROP TABLE"))


def build_scenario_cleanup_test_plan() -> ScenarioExecutionPlan:
    source_fixture: ScenarioFixturePlan = build_scenario_fixture_plan()
    ref_fixture: ScenarioFixturePlan = build_scenario_fixture_plan(
        kind=ScenarioArtifactKind.REF,
        logical_name="stg_customers",
        target_name="__sqb_51b385aebe20__ref__stg_customers",
        sql="SELECT 10 AS customer_id",
    )
    seed_fixture: ScenarioFixturePlan = build_scenario_fixture_plan(
        kind=ScenarioArtifactKind.SEED,
        logical_name="country_codes",
        target_name="__sqb_51b385aebe20__seed__country_codes",
        sql="SELECT 'US' AS country_code",
    )
    model_target: CompiledRelationTarget = CompiledRelationTarget(
        database=None,
        schema="scenario_schema",
        name="__sqb_51b385aebe20__model__daily_revenue",
        qualified_name="scenario_schema.__sqb_51b385aebe20__model__daily_revenue",
    )
    return ScenarioExecutionPlan(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_SCENARIO,
            name="revenue__customer_refund",
        ),
        name="revenue__customer_refund",
        graph_plan=ScenarioGraphPlan(
            key=CompiledObjectKey(
                resource_type=CompiledResourceType.SQL_SCENARIO,
                name="revenue__customer_refund",
            ),
            name="revenue__customer_refund",
            model_names=("daily_revenue",),
        ),
        relation_plan=ScenarioRelationPlan(
            scenario_name="revenue__customer_refund",
            relation_map=ScenarioRelationMap(
                scenario_name="revenue__customer_refund",
                hash_prefix="51b385aebe20",
            ),
            model_targets={
                "daily_revenue": model_target,
                "stg_customers": ref_fixture.target,
            },
            source_fixture_targets={"raw__orders": source_fixture.target},
            ref_fixture_targets={"stg_customers": ref_fixture.target},
            seed_fixture_targets={"country_codes": seed_fixture.target},
        ),
        fixture_plans=(source_fixture, ref_fixture, seed_fixture),
    )
