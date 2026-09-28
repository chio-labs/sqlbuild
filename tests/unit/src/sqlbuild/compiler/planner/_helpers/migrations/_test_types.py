"""Test case types for migration fingerprint helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations.helpers import (
    BASE_CONFIG,
    ORDERS_INPUTS,
)


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
    declared: dict[str, str] = field(default_factory=dict)
    input_columns: dict[tuple[str, str], frozenset[str]] = field(
        default_factory=lambda: dict(ORDERS_INPUTS)
    )


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
    input_columns: dict[tuple[str, str], frozenset[str]] = field(
        default_factory=lambda: dict(ORDERS_INPUTS)
    )


@dataclass(frozen=True)
class UnreadableQueryShapeTestCase:
    description: str
    query_sql: str
    expected_shape: None = None


@dataclass(frozen=True)
class OldNameRowsTestCase:
    description: str
    action: str
    column_aliases: tuple[tuple[str, str], ...]
    grants_supported: bool
    grants_copied: int | None
    reason: str | None
    expected_rows: tuple[str, ...]
