from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
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
    SeedPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
    ScenarioArtifactKind,
)
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCaptureRunResult,
    ScenarioSnapshotColumn,
    ScenarioSnapshotManifest,
    ScenarioSnapshotRelation,
    ScenarioSnapshotStateResult,
)
from sqlbuild.spec.models.schema import default_seed_csv_settings
from tests.unit.src.sqlbuild.executor.scenario.helpers._test_types import (
    ExecuteScenarioSnapshotCaptureStepsTestCase,
    ScenarioSnapshotStateTestCase,
)


def build_snapshot_input_specs_test_plan(
    *, fixture_sql_suffix: str = "", expected_sql_suffix: str = ""
) -> ScenarioExecutionPlan:
    scenario_name: str = "revenue__customer_refund"
    scenario_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SQL_SCENARIO,
        name=scenario_name,
    )
    model_target: CompiledRelationTarget = _target("model", "daily_revenue")

    return ScenarioExecutionPlan(
        key=scenario_key,
        name=scenario_name,
        graph_plan=ScenarioGraphPlan(
            key=scenario_key,
            name=scenario_name,
            target_model_names=("daily_revenue",),
            model_names=("daily_revenue",),
            source_fixture_names=("raw__orders",),
            ref_fixture_names=("stg_customers",),
            seed_names=("country_codes", "currency_codes"),
            seed_fixture_names=("country_codes",),
        ),
        relation_plan=ScenarioRelationPlan(
            scenario_name=scenario_name,
            relation_map=ScenarioRelationMap(
                scenario_name=scenario_name,
                hash_prefix="51b385aebe20",
            ),
        ),
        fixture_plans=(
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.SOURCE,
                logical_name="raw__orders",
                target=_target("source", "raw__orders"),
                sql=f"SELECT 1 AS order_id{fixture_sql_suffix}",
            ),
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.REF,
                logical_name="stg_customers",
                target=_target("ref", "stg_customers"),
                sql="SELECT 10 AS customer_id",
            ),
            ScenarioFixturePlan(
                kind=ScenarioArtifactKind.SEED,
                logical_name="country_codes",
                target=_target("seed", "country_codes"),
                sql="SELECT 'US' AS country_code",
            ),
        ),
        seed_entries=(
            SeedPlanEntry(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SEED,
                    name="currency_codes",
                ),
                name="currency_codes",
                target=_target("seed", "currency_codes"),
                file_path=Path("seeds/currency_codes.csv"),
                columns=(),
                csv_settings=default_seed_csv_settings,
            ),
        ),
        model_entries=(
            ModelPlanEntry(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.MODEL,
                    name="daily_revenue",
                ),
                name="daily_revenue",
                relative_path=Path("models/daily_revenue.sql"),
                materialization_type=MaterializationType.TABLE,
                action=PlanAction.CREATE_TABLE,
                reason=PlanReason.FIRST_RUN,
                target=model_target,
                fingerprint_query_sql="SELECT 75 AS revenue",
                resolved_sql="SELECT 75 AS revenue",
                logical_ddl="CREATE TABLE daily_revenue AS SELECT 75 AS revenue",
            ),
        ),
        expected_checks=(
            ScenarioExpectedCheckPlan(
                model_name="daily_revenue",
                actual_target=model_target,
                expected_sql=f"SELECT 75 AS revenue{expected_sql_suffix}",
            ),
        ),
        assertion_checks=(
            ScenarioAssertionCheckPlan(
                name="no_negative_revenue",
                sql=f"SELECT * FROM daily_revenue WHERE revenue < 0{expected_sql_suffix}",
            ),
        ),
    )


def build_snapshot_manifest(*, input_fingerprint: str = "fresh123") -> ScenarioSnapshotManifest:
    return ScenarioSnapshotManifest(
        version=1,
        scenario_name="revenue__customer_refund",
        captured_at="2026-05-09T00:00:00Z",
        capture_adapter="snowflake",
        capture_dialect="snowflake",
        sqlbuild_version="0.1.0",
        input_fingerprint=input_fingerprint,
        total_rows=2,
        total_bytes=100,
        relations=(
            ScenarioSnapshotRelation(
                kind=ScenarioArtifactKind.SOURCE,
                logical_name="raw__orders",
                file_path=Path("sources/raw__orders.jsonl"),
                row_count=2,
                byte_count=100,
                columns=(
                    ScenarioSnapshotColumn(
                        name="order_id",
                        warehouse_type="NUMBER",
                        local_type="BIGINT",
                    ),
                    ScenarioSnapshotColumn(
                        name="amount",
                        warehouse_type="NUMBER(10,2)",
                        local_type="DECIMAL(10,2)",
                    ),
                ),
            ),
        ),
    )


def write_snapshot_state_test_manifest(
    *, manifest_path: Path, test_case: ScenarioSnapshotStateTestCase
) -> None:
    if test_case.manifest is not None:
        from sqlbuild.executor.scenario.helpers.snapshots import write_scenario_snapshot_manifest

        write_scenario_snapshot_manifest(
            manifest_path=manifest_path,
            manifest=test_case.manifest,
        )
    if test_case.manifest_contents is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(test_case.manifest_contents, encoding="utf-8")


def assert_snapshot_state_error(
    *, state_result: ScenarioSnapshotStateResult, test_case: ScenarioSnapshotStateTestCase
) -> None:
    if test_case.expected_error_fragment is not None:
        assert state_result.error_message is not None
        assert test_case.expected_error_fragment in state_result.error_message


def assert_capture_steps_error(
    *,
    result: ScenarioSnapshotCaptureRunResult,
    test_case: ExecuteScenarioSnapshotCaptureStepsTestCase,
) -> None:
    if test_case.expected_error_fragment is not None:
        assert result.error_message is not None
        assert test_case.expected_error_fragment in result.error_message


def _target(kind: str, logical_name: str) -> CompiledRelationTarget:
    name: str = f"__sqb_51b385aebe20__{kind}__{logical_name}"
    return CompiledRelationTarget(
        database=None,
        schema="scenario_schema",
        name=name,
        qualified_name=f"scenario_schema.{name}",
    )
