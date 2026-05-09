from __future__ import annotations

from typing import Any

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
