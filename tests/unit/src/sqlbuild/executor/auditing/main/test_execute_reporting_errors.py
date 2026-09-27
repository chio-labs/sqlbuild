"""Build audits outside a model node report raised execution errors as error results."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sqlbuild.compiler.auditing.types import AuditOutcome, AuditSeverity
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from tests.unit.src.sqlbuild.executor.auditing.main._test_types import (
    AuditInterruptCase,
    AuditRaisedErrorCase,
)
from tests.unit.src.sqlbuild.executor.auditing.main.helpers import (
    Adapter,
    ErrorResponse,
    build_entry,
    execute_entry_reporting_errors,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AuditRaisedErrorCase(
            description="error-severity audit whose query raises becomes an error result",
            severity=AuditSeverity.ERROR,
            error=RuntimeError("Catalog Error: relation missing"),
            expected_execution_error="Catalog Error: relation missing",
        ),
        AuditRaisedErrorCase(
            description="warn-severity audit whose query raises is an error, like model audits",
            severity=AuditSeverity.WARN,
            error=ValueError("warehouse unavailable"),
            expected_execution_error="warehouse unavailable",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_audit_query_raises_when_executing_build_audit_then_returns_error_result(
    test_case: AuditRaisedErrorCase,
) -> None:
    entry: AuditPlanEntry = replace(build_entry(), severity=test_case.severity)

    result: AuditExecutionResult = execute_entry_reporting_errors(
        entry=entry, adapter=Adapter([ErrorResponse(test_case.error)])
    )

    assert result.outcome == AuditOutcome.ERROR
    assert result.severity == test_case.severity
    assert result.execution_error == test_case.expected_execution_error
    assert result.row_count == 0
    assert result.attached_target_name == "orders"


@pytest.mark.parametrize(
    "test_case",
    [
        AuditInterruptCase(
            description="keyboard interrupt propagates",
            error=KeyboardInterrupt(),
            expected_error_type=KeyboardInterrupt,
        ),
        AuditInterruptCase(
            description="system exit propagates",
            error=SystemExit(2),
            expected_error_type=SystemExit,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_audit_interrupted_when_executing_build_audit_then_interrupt_propagates(
    test_case: AuditInterruptCase,
) -> None:
    with pytest.raises(test_case.expected_error_type):
        execute_entry_reporting_errors(
            entry=build_entry(), adapter=Adapter([ErrorResponse(test_case.error)])
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
