"""Test case types for adapter contract entrypoints."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.types import RelationReadStatus


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
    expected_status: RelationReadStatus | None
    expected_role: str | None = None
    role: str | None = None
