"""Test case types for adapter contract entrypoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SameViewDefinitionTestCase:
    description: str
    definition: str
    sql: str
    expected_match: bool
