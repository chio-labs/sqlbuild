from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import QueryResult
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.helpers.snapshots import (
    build_scenario_snapshot_capture_plan,
    build_scenario_snapshot_manifest_shell,
)
from sqlbuild.executor.scenario.main.capture import execute_scenario_snapshot_capture
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCapturePlan,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureResult,
    ScenarioSnapshotManifest,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.scenario.main._test_types import (
    ExecuteScenarioSnapshotCaptureTestCase,
)
from tests.unit.src.sqlbuild.executor.scenario.main.helpers import (
    build_scenario_cleanup_test_plan_with_project_seed,
)

SCENARIO_PLAN: ScenarioExecutionPlan = build_scenario_cleanup_test_plan_with_project_seed()


class ScenarioSnapshotCaptureTestAdapter(BaseAdapter):
    def __init__(self, *, fail_on_relation: str | None = None) -> None:
        self.fail_on_relation: str | None = fail_on_relation
        self.queries: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def close(self, connection: object) -> None:
        del connection

    def execute(self, connection: object, sql: str) -> object:
        del connection, sql
        return object()

    def query(self, connection: Any, sql: str, *, limit: int | None) -> QueryResult:
        del connection, limit
        self.queries.append(sql)
        if self.fail_on_relation is not None and self.fail_on_relation in sql:
            raise RuntimeError("warehouse read failed")
        if "__sqb_51b385aebe20__source__raw__orders" in sql:
            return QueryResult(
                columns=("order_id", "amount"),
                rows=((1, 10.5), (2, 20)),
            )
        if "__sqb_51b385aebe20__ref__stg_customers" in sql:
            return QueryResult(columns=("customer_id",), rows=((10,),))
        if "__sqb_51b385aebe20__seed__country_codes" in sql:
            return QueryResult(columns=("country_code",), rows=(("US",),))
        raise RuntimeError(f"unexpected query: {sql}")


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioSnapshotCaptureTestCase(
            description="captures materialized scenario inputs into JSONL and manifest",
            expected_result=ScenarioSnapshotCaptureResult(
                scenario_name="revenue__customer_refund",
                status=ExecutionStatus.SUCCESS,
                manifest_path=Path(
                    "/repo/tests/_scenario_snapshots/revenue__customer_refund/scenario.json"
                ),
                manifest=ScenarioSnapshotManifest(
                    version=1,
                    scenario_name="revenue__customer_refund",
                    captured_at="2026-05-09T00:00:00Z",
                    capture_adapter="duckdb",
                    capture_dialect="duckdb",
                    sqlbuild_version="0.1.0",
                    input_fingerprint="placeholder",
                    total_rows=4,
                    total_bytes=97,
                ),
                relation_results=(
                    ScenarioSnapshotCaptureRelationResult(
                        kind=SCENARIO_PLAN.fixture_plans[1].kind,
                        logical_name="stg_customers",
                        source_relation=str(SCENARIO_PLAN.fixture_plans[1].target.qualified_name),
                        file_path=Path("refs/stg_customers.jsonl"),
                        status=ExecutionStatus.SUCCESS,
                        row_count=1,
                        byte_count=19,
                    ),
                    ScenarioSnapshotCaptureRelationResult(
                        kind=ScenarioArtifactKind.SEED,
                        logical_name="country_codes",
                        source_relation=str(SCENARIO_PLAN.seed_entries[0].target.qualified_name),
                        file_path=Path("seeds/country_codes.jsonl"),
                        status=ExecutionStatus.SUCCESS,
                        row_count=1,
                        byte_count=22,
                    ),
                    ScenarioSnapshotCaptureRelationResult(
                        kind=SCENARIO_PLAN.fixture_plans[0].kind,
                        logical_name="raw__orders",
                        source_relation=str(SCENARIO_PLAN.fixture_plans[0].target.qualified_name),
                        file_path=Path("sources/raw__orders.jsonl"),
                        status=ExecutionStatus.SUCCESS,
                        row_count=2,
                        byte_count=56,
                    ),
                ),
            ),
            expected_jsonl_files={
                Path("refs/stg_customers.jsonl"): '{"customer_id":10}\n',
                Path("seeds/country_codes.jsonl"): '{"country_code":"US"}\n',
                Path("sources/raw__orders.jsonl"): (
                    '{"amount":10.5,"order_id":1}\n{"amount":20,"order_id":2}\n'
                ),
            },
            expected_manifest_fragment='"total_rows": 4',
        )
    ],
    ids=["captures materialized scenario inputs into JSONL and manifest"],
)
def test_given_capture_plan_when_executing_snapshot_capture_then_writes_jsonl_and_manifest(
    test_case: ExecuteScenarioSnapshotCaptureTestCase,
    tmp_path: Path,
) -> None:
    capture_plan: ScenarioSnapshotCapturePlan = build_scenario_snapshot_capture_plan(
        project_dir=tmp_path,
        scenario_plan=SCENARIO_PLAN,
    )
    manifest: ScenarioSnapshotManifest = build_scenario_snapshot_manifest_shell(
        capture_plan=capture_plan,
        captured_at="2026-05-09T00:00:00Z",
        capture_adapter="duckdb",
        capture_dialect="duckdb",
        sqlbuild_version="0.1.0",
    )
    adapter: ScenarioSnapshotCaptureTestAdapter = ScenarioSnapshotCaptureTestAdapter()

    result: ScenarioSnapshotCaptureResult = execute_scenario_snapshot_capture(
        capture_plan=capture_plan,
        manifest=manifest,
        adapter=adapter,
        connection=object(),
    )

    assert result.status == test_case.expected_result.status
    assert result.scenario_name == test_case.expected_result.scenario_name
    assert result.manifest is not None
    expected_manifest: ScenarioSnapshotManifest | None = test_case.expected_result.manifest
    assert expected_manifest is not None
    assert result.manifest.total_rows == expected_manifest.total_rows
    assert result.manifest.total_bytes == expected_manifest.total_bytes
    assert (
        tuple(
            ScenarioSnapshotCaptureRelationResult(
                kind=relation.kind,
                logical_name=relation.logical_name,
                source_relation=relation.source_relation,
                file_path=relation.file_path,
                status=relation.status,
                row_count=relation.row_count,
                byte_count=relation.byte_count,
            )
            for relation in result.relation_results
        )
        == test_case.expected_result.relation_results
    )
    for relative_path, expected_contents in test_case.expected_jsonl_files.items():
        assert (capture_plan.snapshot_root / relative_path).read_text(
            encoding="utf-8"
        ) == expected_contents
    assert test_case.expected_manifest_fragment in capture_plan.manifest_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteScenarioSnapshotCaptureTestCase(
            description="returns failed result with relation context when warehouse read fails",
            expected_result=ScenarioSnapshotCaptureResult(
                scenario_name="revenue__customer_refund",
                status=ExecutionStatus.FAILED,
                manifest_path=Path(
                    "/repo/tests/_scenario_snapshots/revenue__customer_refund/scenario.json"
                ),
                relation_results=(
                    ScenarioSnapshotCaptureRelationResult(
                        kind=SCENARIO_PLAN.fixture_plans[1].kind,
                        logical_name="stg_customers",
                        source_relation=str(SCENARIO_PLAN.fixture_plans[1].target.qualified_name),
                        file_path=Path("refs/stg_customers.jsonl"),
                        status=ExecutionStatus.FAILED,
                        error_message=(
                            "Failed to capture ref 'stg_customers': warehouse read failed"
                        ),
                    ),
                ),
                error_message="Failed to capture ref 'stg_customers': warehouse read failed",
            ),
            expected_jsonl_files={},
            expected_manifest_fragment="",
        )
    ],
    ids=["returns failed result with relation context when warehouse read fails"],
)
def test_given_capture_relation_read_failure_when_executing_then_returns_failed_result(
    test_case: ExecuteScenarioSnapshotCaptureTestCase,
    tmp_path: Path,
) -> None:
    capture_plan: ScenarioSnapshotCapturePlan = build_scenario_snapshot_capture_plan(
        project_dir=tmp_path,
        scenario_plan=SCENARIO_PLAN,
    )
    manifest: ScenarioSnapshotManifest = build_scenario_snapshot_manifest_shell(
        capture_plan=capture_plan,
        captured_at="2026-05-09T00:00:00Z",
        capture_adapter="duckdb",
        capture_dialect="duckdb",
        sqlbuild_version="0.1.0",
    )
    adapter: ScenarioSnapshotCaptureTestAdapter = ScenarioSnapshotCaptureTestAdapter(
        fail_on_relation="stg_customers"
    )

    result: ScenarioSnapshotCaptureResult = execute_scenario_snapshot_capture(
        capture_plan=capture_plan,
        manifest=manifest,
        adapter=adapter,
        connection=object(),
    )

    assert result.status == test_case.expected_result.status
    assert result.relation_results == test_case.expected_result.relation_results
    assert result.error_message == test_case.expected_result.error_message
