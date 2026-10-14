from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeEngineParityTestCase:
    """A project whose declaration scope is built natively."""

    description: str
    files: dict[str, str]
    expected_error: str = ""
    expected_minimum_grants: int = 0


@dataclass(frozen=True)
class GeneratedScopeParityTestCase:
    """Seeded scoped projects with minimum coverage of each outcome."""

    description: str
    seed: int
    count: int
    expected_minimum_valid: int
    expected_minimum_invalid: int
    expected_minimum_granting: int


@dataclass(frozen=True)
class ScopeCommandParityTestCase:
    """A project whose `sqb scope` index is built offline."""

    description: str
    files: dict[str, str]
    expected_minimum_grants: int


@dataclass(frozen=True)
class ExpectedNameScanTestCase:
    """Seeded SQL test bodies whose relationship scans match Python's recorded golden."""

    description: str
    syntax: str
    seed: int
    count: int
    expected_minimum_scanned: int
    expected_minimum_errors: int


@dataclass(frozen=True)
class RelationshipEdgeTestCase:
    """SQL texts around Unicode identifier and keyword edges, against Python's golden."""

    description: str
    characters: tuple[str, ...]
    expected_minimum_scanned: int
    expected_minimum_errors: int


@dataclass(frozen=True)
class DeclarationContextParityTestCase:
    """Seeded scoped projects whose consumers resolve declaration contexts under both paths."""

    description: str
    seed: int
    count: int
    expected_minimum_native: int
    expected_minimum_granted: int
    expected_minimum_private: int
    expected_minimum_python_only: int
