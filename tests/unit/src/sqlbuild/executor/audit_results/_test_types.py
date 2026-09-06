"""Dataclass-backed audit result identity test cases."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditResultIdentityTestCase:
    """Expected deterministic identity behavior."""

    description: str
    run_scope_phase: str
    first_attempt_key: str
    second_attempt_key: str
    expected_equal: bool
    expected_first: str | None = None
