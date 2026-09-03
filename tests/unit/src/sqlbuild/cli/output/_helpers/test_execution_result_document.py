"""Aggregate execution result document coverage."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.test.sql_progress import format_parameterized_test_label
from sqlbuild.cli.output._helpers.execution_result_document import (
    _format_model_assets,
    _format_sql_test_checks,
)
from sqlbuild.compiler.discovery.models import SqlTestParameterDeclaration
from sqlbuild.compiler.planner.models import (
    CursorInputEvidence,
    FutureCursorSafetyEvidence,
    MaximumStartSafetyEvidence,
)
from sqlbuild.executor.run.models import (
    MicrobatchAccountingInterval,
    ModelExecutionResult,
)
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.spec.contracts.types import FutureCursorAction
from sqlbuild.sql_values.models import SqlLogicalType, SqlValue
from sqlbuild.sql_values.types import SqlValueKind
from tests.unit.src.sqlbuild.cli.output._helpers._test_types import (
    FutureCursorExecutionProtocolTestCase,
    MicrobatchExecutionProtocolTestCase,
    SqlTestCaseExecutionProtocolTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchExecutionProtocolTestCase(
            description="microbatch execution exposes replay accounting",
            expected_run_type="replay_on_change",
            expected_replay_state="complete_with_unknown_fingerprints",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_microbatch_result_when_formatting_json_then_interval_provenance_is_exposed(
    test_case: MicrobatchExecutionProtocolTestCase,
) -> None:
    result: ModelExecutionResult = ModelExecutionResult(
        model_name="orders",
        status=ExecutionStatus.SUCCESS,
        batch_count=2,
        batch_size="1h",
        microbatch_run_type="replay_on_change",
        microbatch_recovery_batch_count=1,
        microbatch_known_gap_count=1,
        microbatch_unaccounted_interval_count=1,
        microbatch_synthetic_completion_count=1,
        microbatch_unknown_fingerprint_count=1,
        microbatch_contiguous_frontier="2026-01-01T01:00:00",
        microbatch_unaccounted_partition_policy="recover_empty",
        microbatch_replay_requirement_id="requirement-1",
        microbatch_required_model_version_hash="F2",
        microbatch_physical_generation_id="generation-1",
        microbatch_concurrent_enabled=True,
        microbatch_batch_concurrency=2,
        microbatch_global_concurrency=4,
        microbatch_replay_requirement_state="complete_with_unknown_fingerprints",
        microbatch_accounting_intervals=(
            MicrobatchAccountingInterval(
                partition_start="2026-01-01T00:00:00",
                partition_end="2026-01-01T01:00:00",
                accounting_status="synthetic",
                fingerprint_status="unknown",
            ),
        ),
    )

    asset: dict[str, object] = _format_model_assets(results=(result,), plan=None)[0]

    assert asset["microbatch"] == {
        "run_type": test_case.expected_run_type,
        "batch_count": 2,
        "batch_size": "1h",
        "recovery_batch_count": 1,
        "known_gap_count": 1,
        "unaccounted_interval_count": 1,
        "synthetic_completion_count": 1,
        "unknown_fingerprint_count": 1,
        "contiguous_frontier": "2026-01-01T01:00:00",
        "unaccounted_partition_policy": "recover_empty",
        "replay_requirement_id": "requirement-1",
        "required_model_version_hash": "F2",
        "physical_generation_id": "generation-1",
        "concurrent_enabled": True,
        "batch_concurrency": 2,
        "global_concurrency": 4,
        "replay_requirement_state": test_case.expected_replay_state,
        "intervals": [
            {
                "partition_start": "2026-01-01T00:00:00",
                "partition_end": "2026-01-01T01:00:00",
                "accounting_status": "synthetic",
                "fingerprint_status": "unknown",
                "model_version_hash": None,
                "completion_type": None,
                "event_id": None,
            }
        ],
    }


@pytest.mark.parametrize(
    "test_case",
    [FutureCursorExecutionProtocolTestCase("structured future cursor evidence", "cap")],
    ids=lambda case: case.description,
)
def test_given_future_cursor_cap_when_formatting_execution_json_then_structured_evidence_is_exposed(
    test_case: FutureCursorExecutionProtocolTestCase,
) -> None:
    evidence: FutureCursorSafetyEvidence = FutureCursorSafetyEvidence(
        action=FutureCursorAction.CAP,
        max_distance="2d",
        invocation_time="2026-09-01T12:00:00+00:00",
        discovered_start="2500-01-01T00:00:00",
        discovered_end="2500-01-01T00:00:01",
        applied_start="2500-01-01T00:00:00",
        applied_end="2026-09-03T12:00:00",
        maximum_allowed_start="2026-09-03T12:00:00",
        maximum_allowed_end="2026-09-03T12:00:01",
        future_start_detected=True,
        future_end_detected=True,
        determining_relation="raw.events",
        determining_cursor_column="occurred_at",
        inputs=(
            CursorInputEvidence(
                relation="raw.events",
                cursor_column="occurred_at",
                minimum=None,
                maximum="2500-01-01T00:00:00",
            ),
        ),
    )
    result: ModelExecutionResult = ModelExecutionResult(
        model_name="orders",
        status=ExecutionStatus.SUCCESS,
        future_cursor_safety=evidence,
    )

    asset: dict[str, object] = _format_model_assets(results=(result,), plan=None)[0]

    assert asset["future_cursor_safety"] == {
        "action": test_case.expected_action,
        "max_distance": "2d",
        "invocation_time": "2026-09-01T12:00:00+00:00",
        "discovered_bounds": {
            "start": "2500-01-01T00:00:00",
            "end": "2500-01-01T00:00:01",
        },
        "applied_bounds": {
            "start": "2500-01-01T00:00:00",
            "end": "2026-09-03T12:00:00",
        },
        "maximum_allowed_bounds": {
            "start": "2026-09-03T12:00:00",
            "end": "2026-09-03T12:00:01",
        },
        "future_start_detected": True,
        "future_end_detected": True,
        "determining_input": {
            "relation": "raw.events",
            "cursor_column": "occurred_at",
        },
        "inputs": [
            {
                "relation": "raw.events",
                "cursor_column": "occurred_at",
                "minimum": None,
                "maximum": "2500-01-01T00:00:00",
            }
        ],
    }


@pytest.mark.parametrize(
    "test_case",
    [FutureCursorExecutionProtocolTestCase("structured maximum start evidence", "cap")],
    ids=lambda case: case.description,
)
def test_given_maximum_start_cap_when_formatting_execution_json_then_evidence_is_exposed(
    test_case: FutureCursorExecutionProtocolTestCase,
) -> None:
    evidence: MaximumStartSafetyEvidence = MaximumStartSafetyEvidence(
        action=FutureCursorAction.CAP,
        max_ahead="0d",
        invocation_time="2026-09-01T12:00:00+00:00",
        physical_target_max="2026-09-03",
        highest_eligible_target_max="2026-09-01",
        effective_start="2026-08-30T00:00:00",
        maximum_allowed_start="2026-09-01",
        target_relation="analytics.events",
        cursor_column="event_at",
    )
    result: ModelExecutionResult = ModelExecutionResult(
        model_name="events",
        status=ExecutionStatus.SUCCESS,
        maximum_start_safety=evidence,
    )

    asset: dict[str, object] = _format_model_assets(results=(result,), plan=None)[0]

    maximum_start: object = asset["maximum_start_safety"]
    assert maximum_start == {
        "action": test_case.expected_action,
        "max_ahead": "0d",
        "invocation_time": "2026-09-01T12:00:00+00:00",
        "physical_target_max": "2026-09-03",
        "highest_eligible_target_max": "2026-09-01",
        "effective_start": "2026-08-30T00:00:00",
        "maximum_allowed_start": "2026-09-01",
        "input": {"relation": "analytics.events", "cursor_column": "event_at"},
    }


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestCaseExecutionProtocolTestCase(
            description="parameterized SQL test emits stable identity and safe decimal value",
            expected_check_id="sql_test:tests/unit/orders.sql:2:large_order",
            expected_decimal_value="12.3400",
            expected_fingerprint="a" * 64,
            expected_text_label=(
                "order totals [large_order] (tests/unit/orders.sql; "
                'amount:decimal="12.3400", note:string?=null)'
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_parameterized_sql_test_result_when_formatting_json_then_case_metadata_is_safe(
    test_case: SqlTestCaseExecutionProtocolTestCase,
) -> None:
    result: SqlTestExecutionResult = SqlTestExecutionResult(
        test_name="order totals [large_order]",
        outcome=SqlTestOutcome.PASS,
        source_path=Path("tests/unit/orders.sql"),
        block_index=2,
        parent_name="order totals",
        case_name="large_order",
        case_index=1,
        case_fingerprint=test_case.expected_fingerprint,
        parameter_schema=(
            SqlTestParameterDeclaration(
                name="amount",
                value_type=SqlValueKind.DECIMAL,
            ),
            SqlTestParameterDeclaration(
                name="note",
                value_type=SqlValueKind.STRING,
                nullable=True,
            ),
        ),
        parameter_values=(
            (
                "amount",
                SqlValue(
                    logical_type=SqlLogicalType(SqlValueKind.DECIMAL),
                    value=Decimal(test_case.expected_decimal_value),
                ),
            ),
            (
                "note",
                SqlValue(
                    logical_type=SqlLogicalType(SqlValueKind.NULL),
                    value=None,
                ),
            ),
        ),
    )

    check: dict[str, object] = _format_sql_test_checks((result,))[0]

    assert check["check_id"] == test_case.expected_check_id
    assert check["source_path"] == "tests/unit/orders.sql"
    assert check["block_index"] == 2
    assert check["parent_name"] == "order totals"
    assert check["case_name"] == "large_order"
    assert check["case_index"] == 1
    assert check["case_fingerprint"] == test_case.expected_fingerprint
    assert check["parameter_schema"] == (
        {"name": "amount", "type": "decimal", "nullable": False},
        {"name": "note", "type": "string", "nullable": True},
    )
    assert check["parameters"] == (
        {
            "name": "amount",
            "type": "decimal",
            "value": test_case.expected_decimal_value,
        },
        {"name": "note", "type": "string", "value": None},
    )
    assert (
        format_parameterized_test_label(
            name=result.test_name,
            source_path=result.source_path,
            parameter_schema=result.parameter_schema,
            parameter_values=result.parameter_values,
        )
        == test_case.expected_text_label
    )
