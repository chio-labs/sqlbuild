from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedLineageParityTestCase:
    """Seeded generated projects whose fast lineage must not depend on the analysis catalog."""

    description: str
    seed: int
    count: int
    dialects: tuple[str | None, ...]
    expected_minimum_native: int
    expected_minimum_parsed: int
    expected_minimum_star_expansions: int


@dataclass(frozen=True)
class FormerlyDeferredLineageTestCase:
    """Parsed models Python once built, now answered natively or raising Python's error."""

    description: str
    dialect: str
    keeps_catalog: bool
    expected_native_statuses: dict[str, int]
    expected_error: str | None


@dataclass(frozen=True)
class UnparsedLineageTestCase:
    """A model without compact facts whose SQL does not parse, so it has no fast lineage."""

    description: str
    query_sql: str
    expected_status: str
    expected_messages: tuple[str, ...]
