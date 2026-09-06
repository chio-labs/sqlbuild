"""Test-case models for audit-factory authoring."""

from dataclasses import dataclass

from sqlbuild.compiler.auditing.types import ThresholdOperator


@dataclass(frozen=True)
class AuditDecoratorTestCase:
    description: str
    expected_bare_name: str
    expected_called_name: str


@dataclass(frozen=True)
class AuditThresholdHelperTestCase:
    description: str
    lower: float
    upper: float
    expected_operator: ThresholdOperator


@dataclass(frozen=True)
class InvalidAuditCaseNameTestCase:
    description: str
    name: str
    expected_error_fragment: str
