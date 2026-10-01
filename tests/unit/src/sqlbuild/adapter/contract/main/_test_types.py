"""Test case types for adapter contract entrypoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SameViewDefinitionTestCase:
    description: str
    definition: str
    sql: str
    expected_match: bool


@dataclass(frozen=True)
class RelationProbeClassificationTestCase:
    description: str
    adapter_name: str
    errors: tuple[Exception, ...]
    expected_exists: bool | None
