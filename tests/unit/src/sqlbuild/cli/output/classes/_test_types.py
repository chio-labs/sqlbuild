"""Test-case types for compatibility event projection."""

from dataclasses import dataclass

from sqlbuild.runtime.observability.types import JSONValue


@dataclass(frozen=True)
class CompatibilityProjectionTestCase:
    """One compatibility projection expectation."""

    description: str
    expected_output: object


@dataclass(frozen=True)
class PythonCheckProjectionTestCase:
    """One Python-check terminal projection expectation."""

    description: str
    event_type: str
    passed: bool
    severity: str
    payload: dict[str, JSONValue]
    expected_status: str
