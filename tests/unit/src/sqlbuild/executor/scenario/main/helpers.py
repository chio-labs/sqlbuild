from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, QueryResult, StatementRecorder
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    ScenarioExecutionPlan,
    ScenarioFixturePlan,
    ScenarioGraphPlan,
    ScenarioRelationMap,
    ScenarioRelationPlan,
    SeedPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
    ScenarioArtifactKind,
)
from sqlbuild.spec.models.schema import SeedCsvSettings, default_seed_csv_settings


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


class ScenarioSnapshotCaptureStepsTestAdapter(BaseAdapter):
    """Adapter that records capture orchestration operations."""

    def __init__(
        self,
        *,
        fail_on_create_target: str | None = None,
        fail_on_seed: bool = False,
        fail_on_query_target: str | None = None,
    ) -> None:
        self.fail_on_create_target: str | None = fail_on_create_target
        self.fail_on_seed: bool = fail_on_seed
        self.fail_on_query_target: str | None = fail_on_query_target
        self.events: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def execute(self, connection: object, sql: str) -> object:
        del connection
        self.events.append(sql)
        return object()

    def close(self, connection: object) -> None:
        del connection

    def create_table_as(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        config: dict[str, Any] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, sql, config
        self.events.append(f"create:{destination}")
        if self.fail_on_create_target is not None and self.fail_on_create_target in destination:
            raise RuntimeError("fixture create failed")
        statement_recorder.record(f"CREATE TABLE {destination}")

    def drop(
        self,
        connection: Any,
        *,
        destination: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, if_exists
        self.events.append(f"drop:{destination}")
        statement_recorder.record(f"DROP TABLE {destination}")

    def load_seed(
        self,
        connection: Any,
        *,
        destination: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        csv_settings: SeedCsvSettings = default_seed_csv_settings,
        replace: bool = True,
        infer_types: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, file_path, columns, csv_settings, replace, infer_types
        self.events.append(f"seed:{destination}")
        if self.fail_on_seed:
            raise RuntimeError("seed load failed")
        statement_recorder.record(f"LOAD SEED {destination}")

    def query(self, connection: Any, sql: str, *, limit: int | None) -> QueryResult:
        del connection, limit
        self.events.append(f"query:{sql}")
        if self.fail_on_query_target is not None and self.fail_on_query_target in sql:
            raise RuntimeError("warehouse read failed")
        if "COUNT(*)" in sql and "__sqb_51b385aebe20__source__raw__orders" in sql:
            return QueryResult(columns=("count",), rows=((1,),))
        if "COUNT(*)" in sql and "__sqb_51b385aebe20__ref__stg_customers" in sql:
            return QueryResult(columns=("count",), rows=((1,),))
        if "COUNT(*)" in sql and "__sqb_51b385aebe20__seed__country_codes" in sql:
            return QueryResult(columns=("count",), rows=((1,),))
        if "__sqb_51b385aebe20__source__raw__orders" in sql:
            return QueryResult(columns=("order_id",), rows=((1,),))
        if "__sqb_51b385aebe20__ref__stg_customers" in sql:
            return QueryResult(columns=("customer_id",), rows=((10,),))
        if "__sqb_51b385aebe20__seed__country_codes" in sql:
            return QueryResult(columns=("country_code",), rows=(("US",),))
        raise RuntimeError(f"unexpected query: {sql}")

    def describe_relation(self, connection: Any, relation: str) -> tuple[ColumnInfo, ...]:
        del connection
        if "__sqb_51b385aebe20__source__raw__orders" in relation:
            return (ColumnInfo(name="order_id", type="INTEGER"),)
        if "__sqb_51b385aebe20__ref__stg_customers" in relation:
            return (ColumnInfo(name="customer_id", type="INTEGER"),)
        if "__sqb_51b385aebe20__seed__country_codes" in relation:
            return (ColumnInfo(name="country_code", type="VARCHAR"),)
        raise RuntimeError(f"unexpected describe: {relation}")


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
        destination=CompiledRelationLocation(
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
    return tuple(sql for sql in adapter.executed_sql if sql.startswith("DROP "))


def build_scenario_cleanup_test_plan(
    *, model_materialization_type: MaterializationType = MaterializationType.TABLE
) -> ScenarioExecutionPlan:
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
    model_target: CompiledRelationLocation = CompiledRelationLocation(
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
            model_locations={
                "daily_revenue": model_target,
                "stg_customers": ref_fixture.destination,
            },
            source_fixture_locations={"raw__orders": source_fixture.destination},
            ref_fixture_locations={"stg_customers": ref_fixture.destination},
            seed_fixture_locations={"country_codes": seed_fixture.destination},
        ),
        fixture_plans=(source_fixture, ref_fixture, seed_fixture),
        model_entries=(
            ModelPlanEntry(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.MODEL,
                    name="daily_revenue",
                ),
                name="daily_revenue",
                relative_path=Path("models/daily_revenue.sql"),
                materialization_type=model_materialization_type,
                action=PlanAction.CREATE_TABLE,
                reason=PlanReason.FIRST_RUN,
                destination=model_target,
                fingerprint_query_sql="SELECT 1 AS revenue",
                resolved_sql="SELECT 1 AS revenue",
                logical_ddl="CREATE TABLE daily_revenue AS SELECT 1 AS revenue",
            ),
        ),
    )


def build_scenario_cleanup_test_plan_with_project_seed() -> ScenarioExecutionPlan:
    plan: ScenarioExecutionPlan = build_scenario_cleanup_test_plan()
    seed_target: CompiledRelationLocation = CompiledRelationLocation(
        database=None,
        schema="scenario_schema",
        name="__sqb_51b385aebe20__seed__country_codes",
        qualified_name="scenario_schema.__sqb_51b385aebe20__seed__country_codes",
    )
    return ScenarioExecutionPlan(
        key=plan.key,
        name=plan.name,
        graph_plan=plan.graph_plan,
        relation_plan=plan.relation_plan,
        fixture_plans=plan.fixture_plans[:2],
        seed_entries=(
            SeedPlanEntry(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SEED,
                    name="country_codes",
                ),
                name="country_codes",
                destination=seed_target,
                file_path=Path("seeds/country_codes.csv"),
                columns=(),
                csv_settings=default_seed_csv_settings,
            ),
        ),
    )


def build_scenario_model_test_plan(
    *, model_entries: tuple[ModelPlanEntry, ...]
) -> ScenarioExecutionPlan:
    source_target: CompiledRelationLocation = CompiledRelationLocation(
        database=None,
        schema="scenario_schema",
        name="__sqb_51b385aebe20__source__raw__orders",
        qualified_name="scenario_schema.__sqb_51b385aebe20__source__raw__orders",
    )
    seed_target: CompiledRelationLocation = CompiledRelationLocation(
        database=None,
        schema="scenario_schema",
        name="__sqb_51b385aebe20__seed__country_codes",
        qualified_name="scenario_schema.__sqb_51b385aebe20__seed__country_codes",
    )
    model_locations: dict[str, CompiledRelationLocation] = {
        entry.name: entry.destination for entry in model_entries
    }
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
            model_names=tuple(entry.name for entry in model_entries),
            source_fixture_names=("raw__orders",),
            seed_names=("country_codes",),
        ),
        relation_plan=ScenarioRelationPlan(
            scenario_name="revenue__customer_refund",
            relation_map=ScenarioRelationMap(
                scenario_name="revenue__customer_refund",
                hash_prefix="51b385aebe20",
            ),
            model_locations=model_locations,
            seed_locations={"country_codes": seed_target},
            source_fixture_locations={"raw__orders": source_target},
            source_map={},
        ),
        model_entries=model_entries,
    )


def build_scenario_model_entry(
    *,
    name: str = "daily_revenue",
    target_name: str = "__sqb_51b385aebe20__model__daily_revenue",
    resolved_sql: str = "SELECT * FROM scenario_schema.__sqb_51b385aebe20__source__raw__orders",
    materialization_type: MaterializationType = MaterializationType.TABLE,
    action: PlanAction = PlanAction.CREATE_TABLE,
) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=materialization_type,
        action=action,
        reason=PlanReason.FIRST_RUN,
        destination=CompiledRelationLocation(
            database=None,
            schema="scenario_schema",
            name=target_name,
            qualified_name=f"scenario_schema.{target_name}",
        ),
        fingerprint_query_sql=resolved_sql,
        resolved_sql=resolved_sql,
        logical_ddl="",
    )
