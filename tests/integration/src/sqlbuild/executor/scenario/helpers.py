from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationTarget,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    ScenarioAssertionCheckPlan,
    ScenarioExecutionPlan,
    ScenarioExpectedCheckPlan,
    ScenarioFixturePlan,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
)
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
    ScenarioArtifactKind,
)

SCENARIO_NAME: str = "revenue__customer_refund"
SCHEMA_NAME: str = "scenario_schema"
HASH_PREFIX: str = "51b385aebe20"


def build_duckdb_fixture_plans() -> tuple[ScenarioFixturePlan, ...]:
    return (
        _fixture_plan(
            kind=ScenarioArtifactKind.SOURCE,
            logical_name="raw__orders",
            physical_name="__sqb_51b385aebe20__source__raw__orders",
            sql=(
                "WITH helper_orders AS ("
                "SELECT 1 AS order_id, 10 AS customer_id, 'US' AS country_code"
                ") SELECT * FROM helper_orders"
            ),
        ),
        _fixture_plan(
            kind=ScenarioArtifactKind.REF,
            logical_name="stg_customers",
            physical_name="__sqb_51b385aebe20__ref__stg_customers",
            sql="SELECT 10 AS customer_id, 'Ada' AS customer_name",
        ),
        _fixture_plan(
            kind=ScenarioArtifactKind.SEED,
            logical_name="country_codes",
            physical_name="__sqb_51b385aebe20__seed__country_codes",
            sql="SELECT 'US' AS country_code, 'United States' AS country_name",
        ),
    )


def build_duckdb_invalid_fixture_plan() -> ScenarioFixturePlan:
    return _fixture_plan(
        kind=ScenarioArtifactKind.SOURCE,
        logical_name="raw__orders",
        physical_name="__sqb_51b385aebe20__source__raw__orders",
        sql="SELECT * FROM missing_relation",
    )


def build_duckdb_cleanup_plan() -> ScenarioExecutionPlan:
    fixture_plans: tuple[ScenarioFixturePlan, ...] = build_duckdb_fixture_plans()
    ref_fixture: ScenarioFixturePlan = fixture_plans[1]
    model_target: CompiledRelationTarget = _target(
        physical_name="__sqb_51b385aebe20__model__daily_revenue"
    )
    return ScenarioExecutionPlan(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_SCENARIO,
            name=SCENARIO_NAME,
        ),
        name=SCENARIO_NAME,
        graph_plan=ScenarioGraphPlan(
            key=CompiledObjectKey(
                resource_type=CompiledResourceType.SQL_SCENARIO,
                name=SCENARIO_NAME,
            ),
            name=SCENARIO_NAME,
            model_names=("daily_revenue",),
        ),
        relation_plan=ScenarioRelationPlan(
            scenario_name=SCENARIO_NAME,
            relation_map=ScenarioRelationMap(
                scenario_name=SCENARIO_NAME,
                hash_prefix=HASH_PREFIX,
            ),
            model_targets={
                "daily_revenue": model_target,
                "stg_customers": ref_fixture.target,
            },
            ref_fixture_targets={"stg_customers": ref_fixture.target},
        ),
        fixture_plans=fixture_plans,
    )


def build_duckdb_model_execution_plan() -> ScenarioExecutionPlan:
    source_target: CompiledRelationTarget = _target(
        physical_name="__sqb_51b385aebe20__source__raw__orders"
    )
    ref_target: CompiledRelationTarget = _target(
        physical_name="__sqb_51b385aebe20__ref__stg_customers"
    )
    seed_target: CompiledRelationTarget = _target(
        physical_name="__sqb_51b385aebe20__seed__country_codes"
    )
    stg_orders_target: CompiledRelationTarget = _target(
        physical_name="__sqb_51b385aebe20__model__stg_orders"
    )
    daily_revenue_target: CompiledRelationTarget = _target(
        physical_name="__sqb_51b385aebe20__model__daily_revenue"
    )
    stg_orders: ModelPlanEntry = _model_entry(
        name="stg_orders",
        target=stg_orders_target,
        sql=(
            "SELECT o.order_id, o.customer_id, c.country_name "
            "FROM scenario_schema.__sqb_51b385aebe20__source__raw__orders o "
            "JOIN scenario_schema.__sqb_51b385aebe20__seed__country_codes c "
            "ON o.country_code = c.country_code"
        ),
    )
    daily_revenue: ModelPlanEntry = _model_entry(
        name="daily_revenue",
        target=daily_revenue_target,
        sql=(
            "SELECT o.order_id, c.customer_name, o.country_name "
            "FROM scenario_schema.__sqb_51b385aebe20__model__stg_orders o "
            "JOIN scenario_schema.__sqb_51b385aebe20__ref__stg_customers c "
            "ON o.customer_id = c.customer_id"
        ),
    )
    return ScenarioExecutionPlan(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_SCENARIO,
            name=SCENARIO_NAME,
        ),
        name=SCENARIO_NAME,
        graph_plan=ScenarioGraphPlan(
            key=CompiledObjectKey(
                resource_type=CompiledResourceType.SQL_SCENARIO,
                name=SCENARIO_NAME,
            ),
            name=SCENARIO_NAME,
            model_names=("stg_orders", "daily_revenue"),
            source_fixture_names=("raw__orders",),
            ref_fixture_names=("stg_customers",),
            seed_names=("country_codes",),
        ),
        relation_plan=ScenarioRelationPlan(
            scenario_name=SCENARIO_NAME,
            relation_map=ScenarioRelationMap(
                scenario_name=SCENARIO_NAME,
                hash_prefix=HASH_PREFIX,
            ),
            model_targets={
                "stg_orders": stg_orders_target,
                "daily_revenue": daily_revenue_target,
                "stg_customers": ref_target,
            },
            seed_targets={"country_codes": seed_target},
            source_fixture_targets={"raw__orders": source_target},
            ref_fixture_targets={"stg_customers": ref_target},
        ),
        fixture_plans=build_duckdb_fixture_plans()[:2],
        model_entries=(stg_orders, daily_revenue),
    )


def build_duckdb_expected_check_plan(*, expected_sql: str) -> ScenarioExecutionPlan:
    model_target: CompiledRelationTarget = _target(
        physical_name="__sqb_51b385aebe20__model__daily_revenue"
    )
    return ScenarioExecutionPlan(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_SCENARIO,
            name=SCENARIO_NAME,
        ),
        name=SCENARIO_NAME,
        graph_plan=ScenarioGraphPlan(
            key=CompiledObjectKey(
                resource_type=CompiledResourceType.SQL_SCENARIO,
                name=SCENARIO_NAME,
            ),
            name=SCENARIO_NAME,
            model_names=("daily_revenue",),
        ),
        relation_plan=ScenarioRelationPlan(
            scenario_name=SCENARIO_NAME,
            relation_map=ScenarioRelationMap(
                scenario_name=SCENARIO_NAME,
                hash_prefix=HASH_PREFIX,
            ),
            model_targets={"daily_revenue": model_target},
        ),
        expected_checks=(
            ScenarioExpectedCheckPlan(
                model_name="daily_revenue",
                actual_target=model_target,
                expected_sql=expected_sql,
            ),
        ),
    )


def build_duckdb_assertion_check_plan(*, assertion_sql: str) -> ScenarioExecutionPlan:
    return ScenarioExecutionPlan(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SQL_SCENARIO,
            name=SCENARIO_NAME,
        ),
        name=SCENARIO_NAME,
        graph_plan=ScenarioGraphPlan(
            key=CompiledObjectKey(
                resource_type=CompiledResourceType.SQL_SCENARIO,
                name=SCENARIO_NAME,
            ),
            name=SCENARIO_NAME,
            model_names=("daily_revenue",),
        ),
        relation_plan=ScenarioRelationPlan(
            scenario_name=SCENARIO_NAME,
            relation_map=ScenarioRelationMap(
                scenario_name=SCENARIO_NAME,
                hash_prefix=HASH_PREFIX,
            ),
        ),
        assertion_checks=(
            ScenarioAssertionCheckPlan(
                name="no_unknown_customers",
                sql=assertion_sql,
            ),
        ),
    )


def relation_rows(connection: Any, relation_name: str) -> tuple[tuple[object, ...], ...]:
    rows: list[Any] = connection.execute(f"SELECT * FROM {SCHEMA_NAME}.{relation_name}").fetchall()
    return tuple(tuple(row) for row in rows)


def relation_exists(connection: Any, relation_name: str) -> bool:
    row: Any | None = connection.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
        [SCHEMA_NAME, relation_name],
    ).fetchone()
    return row is not None


def create_table(connection: Any, relation_name: str, sql: str = "SELECT 1 AS value") -> None:
    connection.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")
    connection.execute(f"CREATE TABLE {SCHEMA_NAME}.{relation_name} AS {sql}")


def _fixture_plan(
    *,
    kind: ScenarioArtifactKind,
    logical_name: str,
    physical_name: str,
    sql: str,
) -> ScenarioFixturePlan:
    return ScenarioFixturePlan(
        kind=kind,
        logical_name=logical_name,
        target=_target(physical_name=physical_name),
        sql=sql,
    )


def _target(*, physical_name: str) -> CompiledRelationTarget:
    return CompiledRelationTarget(
        database=None,
        schema=SCHEMA_NAME,
        name=physical_name,
        qualified_name=f"{SCHEMA_NAME}.{physical_name}",
    )


def _model_entry(*, name: str, target: CompiledRelationTarget, sql: str) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.FIRST_RUN,
        target=target,
        fingerprint_query_sql=sql,
        resolved_sql=sql,
        logical_ddl="",
    )
