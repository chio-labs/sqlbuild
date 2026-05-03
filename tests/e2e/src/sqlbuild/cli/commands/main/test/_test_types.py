"""Test types for test command e2e tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SqlTestE2ETestCase:
    """Test case for sqb test e2e verification."""

    description: str
    expected_exit_code: int
    expected_stdout_fragment: str
