from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedLineageParityTestCase:
    """Seeded generated projects whose fast lineage Python and the native engine must agree on."""

    description: str
    seed: int
    count: int
    dialects: tuple[str | None, ...]
    expected_minimum_native: int
    expected_minimum_parsed: int
    expected_minimum_star_expansions: int


@dataclass(frozen=True)
class DeferredLineageTestCase:
    """Parsed models the native engine hands back to Python, which records each deferral."""

    description: str
    dialect: str
    keeps_catalog: bool
    expected_native_statuses: dict[str, int]
    expected_kind: str


@dataclass(frozen=True)
class UnparsedLineageTestCase:
    """A model without compact facts whose SQL does not parse, so it has no fast lineage."""

    description: str
    query_sql: str
    expected_status: str
    expected_messages: tuple[str, ...]
