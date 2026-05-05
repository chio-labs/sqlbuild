"""Test case types for SQL test pipeline helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SqlTestFunctionPreflightTestCase:
    """One SQL test function preflight scenario."""

    description: str
    expected_outcome: str
    expected_error_fragment: str
