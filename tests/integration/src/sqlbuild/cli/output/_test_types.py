"""Test case models for CLI output integration coverage."""

from dataclasses import dataclass

from sqlbuild.compiler.auditing.types import AuditOutcome


@dataclass(frozen=True)
class MeasurementEnvelopeTestCase:
    description: str
    outcome: AuditOutcome
    expected_status: str
    expected_passed: bool
