"""Test types for audit command e2e tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditE2ETestCase:
    """Test case for sqb audit e2e verification."""

    description: str
    expected_exit_code: int
    expected_stdout_fragment: str
