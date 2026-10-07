from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthoredSqlParityTestCase:
    """Seeded authored SQL expanded by the Python engine and by the preview engine."""

    description: str
    seed: int
    count: int
    expected_minimum_expanded: int
    expected_minimum_python_errors: int
