"""Test-case types for terminal integration-result projection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TerminalProjectionTestCase:
    """One terminal projection expectation."""

    description: str
    expected_output: object


@dataclass(frozen=True)
class EnvelopeFieldValidationTestCase:
    """One malformed top-level integration envelope field."""

    description: str
    field_name: str
    value: object
    expected_error: str


@dataclass(frozen=True)
class StructuralMetadataValidationTestCase:
    """One unsafe framework structural metadata mapping."""

    description: str
    value: object
    expected_error: str


@dataclass(frozen=True)
class MaximumStartMetadataValidationTestCase:
    """One maximum-start structural metadata validation case."""

    description: str
    value: object
    expected_error: str


@dataclass(frozen=True)
class IntegrationActionContractTestCase:
    """One canonical action expected to remain valid in integration output."""

    description: str
    expected_action: str


@dataclass(frozen=True)
class ProjectionDegradationTestCase:
    """Expected behavior after optional integration projection fails."""

    description: str
    expected_warning: str
    expected_degraded: bool
