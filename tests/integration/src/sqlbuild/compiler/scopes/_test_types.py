from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeEngineParityTestCase:
    """A project whose declaration scope is built under each compiler engine."""

    description: str
    files: dict[str, str]
    expected_error: str = ""
    expected_minimum_grants: int = 0


@dataclass(frozen=True)
class GeneratedScopeParityTestCase:
    """Seeded scoped projects compared between engines, with minimum coverage of each outcome."""

    description: str
    seed: int
    count: int
    expected_minimum_valid: int
    expected_minimum_invalid: int
    expected_minimum_granting: int
    expected_mismatches: tuple[tuple[object, object, object], ...] = ()


@dataclass(frozen=True)
class ScopeCommandParityTestCase:
    """A project whose `sqb scope` index is built offline under each compiler engine."""

    description: str
    files: dict[str, str]
    expected_minimum_grants: int
