"""Measurement audit execution tests."""

from __future__ import annotations

import pytest

import sqlbuild.executor.auditing._helpers.execution as execute_module
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.executor.auditing.models import AuditExecutionResult
from tests.unit.src.sqlbuild.executor.auditing.main._test_types import (
    AuditExecutionCase,
    InvalidMeasurementCase,
    MeasurementOutcomeCase,
    MeasurementRowCountCase,
    NullMeasurementOutcomeCase,
)
from tests.unit.src.sqlbuild.executor.auditing.main.helpers import (
    Adapter,
    Cursor,
    ErrorResponse,
    build_entry,
    execute_entry,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MeasurementRowCountCase("zero rows", 0, "returned 0"),
        MeasurementRowCountCase("multiple rows", 2, "returned 2"),
    ],
    ids=lambda case: case.description,
)
def test_given_non_single_measurement_row_when_executed_then_returns_execution_error(
    test_case: MeasurementRowCountCase,
) -> None:
    adapter: Adapter = Adapter(
        [Cursor(columns=("valid_rate", "total_rows"), rows=[(95, 10)] * test_case.row_count)]
    )
    result: AuditExecutionResult = execute_entry(entry=build_entry(), adapter=adapter)
    assert result.outcome == AuditOutcome.ERROR
    assert result.execution_error is not None
    assert test_case.expected_error in result.execution_error
    assert result.row_count == 0


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidMeasurementCase(
            "missing value", ("other", "total_rows"), (95, 10), "missing value column"
        ),
        InvalidMeasurementCase(
            "null value", ("valid_rate", "total_rows"), (None, 10), "must not be NULL"
        ),
        InvalidMeasurementCase(
            "text value", ("valid_rate", "total_rows"), ("95", 10), "must be numeric"
        ),
        InvalidMeasurementCase(
            "missing count", ("valid_rate", "other"), (95, 10), "missing sample count column"
        ),
        InvalidMeasurementCase(
            "negative count", ("valid_rate", "total_rows"), (95, -1), "non-negative integer"
        ),
        InvalidMeasurementCase(
            "fraction count", ("valid_rate", "total_rows"), (95, 1.5), "non-negative integer"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_measurement_columns_when_executed_then_returns_clear_error(
    test_case: InvalidMeasurementCase,
) -> None:
    result: AuditExecutionResult = execute_entry(
        entry=build_entry(),
        adapter=Adapter([Cursor(columns=test_case.columns, rows=[test_case.row])]),
    )
    assert result.outcome == AuditOutcome.ERROR
    assert result.execution_error is not None
    assert test_case.expected_error in result.execution_error


@pytest.mark.parametrize(
    "test_case",
    [
        MeasurementOutcomeCase("pass", 100, 10, AuditOutcome.PASS),
        MeasurementOutcomeCase("warn", 95, 10, AuditOutcome.WARN),
        MeasurementOutcomeCase("error", 89, 10, AuditOutcome.ERROR),
        MeasurementOutcomeCase("low samples", 89, 4, AuditOutcome.INSUFFICIENT),
        MeasurementOutcomeCase("absent samples", 95, None, AuditOutcome.INSUFFICIENT),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_measurement_when_executed_then_maps_outcome(
    test_case: MeasurementOutcomeCase,
) -> None:
    result: AuditExecutionResult = execute_entry(
        entry=build_entry(),
        adapter=Adapter(
            [
                Cursor(
                    columns=("VALID_RATE", "TOTAL_ROWS"),
                    rows=[(test_case.value, test_case.sample_count)],
                )
            ]
        ),
    )
    assert result.outcome == test_case.expected_outcome
    assert result.measured_value == float(test_case.value)
    assert result.sample_count == test_case.sample_count
    assert result.row_count == 0


@pytest.mark.parametrize(
    "test_case",
    [NullMeasurementOutcomeCase("zero samples", 0, AuditOutcome.INSUFFICIENT)],
    ids=lambda case: case.description,
)
def test_given_null_measurement_with_too_few_samples_when_executed_then_is_insufficient(
    test_case: NullMeasurementOutcomeCase,
) -> None:
    result: AuditExecutionResult = execute_entry(
        entry=build_entry(),
        adapter=Adapter(
            [Cursor(columns=("VALID_RATE", "TOTAL_ROWS"), rows=[(None, test_case.sample_count)])]
        ),
    )

    assert result.outcome == test_case.expected_outcome
    assert result.measured_value is None
    assert result.sample_count == test_case.sample_count
    assert result.execution_error is None


@pytest.mark.parametrize(
    "test_case",
    [AuditExecutionCase("row limit", AuditOutcome.WARN)],
    ids=lambda case: case.description,
)
def test_given_warning_with_evidence_limit_when_executed_then_retains_bounded_safe_rows(
    test_case: AuditExecutionCase,
) -> None:
    adapter: Adapter = Adapter(
        [
            Cursor(columns=("valid_rate", "total_rows"), rows=[(95, 10)]),
            Cursor(columns=("id", "value"), rows=[(1, object()), (2, "b"), (3, "c")]),
        ]
    )
    result: AuditExecutionResult = execute_entry(
        entry=build_entry(evidence_sql="SELECT evidence", evidence_limit=2), adapter=adapter
    )
    assert result.outcome == test_case.expected_outcome
    assert len(result.evidence_rows) == 2
    assert isinstance(result.evidence_rows[0]["value"], str)
    assert result.evidence_truncated is True


@pytest.mark.parametrize(
    "test_case",
    [AuditExecutionCase("byte limit", AuditOutcome.WARN)],
    ids=lambda case: case.description,
)
def test_given_oversized_evidence_when_executed_then_drops_trailing_rows(
    test_case: AuditExecutionCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(execute_module, "MAX_EVIDENCE_SERIALIZED_BYTES", 25)
    adapter: Adapter = Adapter(
        [
            Cursor(columns=("valid_rate", "total_rows"), rows=[(95, 10)]),
            Cursor(columns=("value",), rows=[("short",), ("too long for ceiling",)]),
        ]
    )
    result: AuditExecutionResult = execute_entry(
        entry=build_entry(evidence_sql="SELECT evidence"), adapter=adapter
    )
    assert result.outcome == test_case.expected_outcome
    assert result.evidence_rows == ({"value": "short"},)
    assert result.evidence_truncated is True


@pytest.mark.parametrize(
    "test_case",
    [AuditExecutionCase("query failure", AuditOutcome.WARN)],
    ids=lambda case: case.description,
)
def test_given_failing_evidence_query_when_executed_then_preserves_measurement_outcome(
    test_case: AuditExecutionCase,
) -> None:
    adapter: Adapter = Adapter(
        [
            Cursor(columns=("valid_rate", "total_rows"), rows=[(95, 10)]),
            ErrorResponse(RuntimeError("evidence unavailable")),
        ]
    )
    result: AuditExecutionResult = execute_entry(
        entry=build_entry(evidence_sql="SELECT evidence"), adapter=adapter
    )
    assert result.outcome == test_case.expected_outcome
    assert result.evidence_error == "RuntimeError: evidence unavailable"


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
