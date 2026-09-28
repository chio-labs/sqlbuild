"""Test case types for migration fingerprint helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations.helpers import BASE_CONFIG


@dataclass(frozen=True)
class MigrationFingerprintTestCase:
    description: str
    origin_sql: str
    destination_sql: str
    expected_match: bool
    origin_config: dict[str, object] = field(default_factory=lambda: dict(BASE_CONFIG))
    destination_config: dict[str, object] = field(default_factory=lambda: dict(BASE_CONFIG))
    destination_ref_identities: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IneligibleFingerprintTestCase:
    description: str
    query_sql: str
    expected_fingerprint: str | None


@dataclass(frozen=True)
class IdenticalRenameTestCase:
    description: str
    previous_sql: str
    current_sql: str
    expected_renames: tuple[tuple[str, str], ...]
    excluded: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RenameHintTestCase:
    description: str
    previous_sql: str
    current_sql: str
    live_columns: frozenset[str]
    expected_hints: tuple[str, ...]


@dataclass(frozen=True)
class RenameExplainsChangeTestCase:
    description: str
    previous_sql: str
    current_sql: str
    renames: dict[str, str]
    expected_explained: bool


@dataclass(frozen=True)
class UnreadableQueryShapeTestCase:
    description: str
    query_sql: str
    expected_shape: None = None
