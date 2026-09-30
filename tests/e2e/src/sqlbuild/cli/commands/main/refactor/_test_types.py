"""Test case types for `sqb rename` and `sqb mv` e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelRefactorE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_removed: str
    expected_file: str
    expected_fragments: dict[str, tuple[str, ...]]
    expected_relation: str
    extra_files: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelMigrationE2ETestCase:
    description: str
    materialized: str
    udf: bool
    expected_declaration: str
    expected_migrate_from_count: int
    expected_old_name_type: str
    expected_order_ids: tuple[int, ...]


@dataclass(frozen=True)
class ColumnRenameE2ETestCase:
    description: str
    command: tuple[str, ...]
    extra_files: dict[str, str] = field(default_factory=dict)
    expected_fragments: dict[str, tuple[str, ...]] = field(default_factory=dict)
    expected_columns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    expected_manual: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefusedRefactorE2ETestCase:
    description: str
    command: tuple[str, ...]
    extra_files: dict[str, str]
    expected_status: str
    expected_reason: str


@dataclass(frozen=True)
class ColumnMigrationE2ETestCase:
    description: str
    expected_declaration: str
    expected_columns: tuple[str, ...]
    expected_order_ids: tuple[int, ...]


@dataclass(frozen=True)
class DryRunE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_paths: frozenset[str]
