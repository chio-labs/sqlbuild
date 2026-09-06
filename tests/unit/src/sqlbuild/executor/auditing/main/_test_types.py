"""Measurement audit execution test cases."""

from dataclasses import dataclass

from sqlbuild.compiler.auditing.types import AuditOutcome


@dataclass(frozen=True)
class MeasurementRowCountCase:
    description: str
    row_count: int
    expected_error: str


@dataclass(frozen=True)
class InvalidMeasurementCase:
    description: str
    columns: tuple[str, str]
    row: tuple[object, object]
    expected_error: str


@dataclass(frozen=True)
class MeasurementOutcomeCase:
    description: str
    value: int
    sample_count: int | None
    expected_outcome: AuditOutcome


@dataclass(frozen=True)
class AuditExecutionCase:
    description: str
    expected_outcome: AuditOutcome
