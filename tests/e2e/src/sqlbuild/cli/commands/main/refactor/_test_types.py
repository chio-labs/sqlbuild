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
    expected_old_name_type: str
    expected_order_ids: tuple[int, ...]
    extra_files: dict[str, str] = field(default_factory=dict)
    removed_files: tuple[str, ...] = ()
    stripped_fingerprints: tuple[str, ...] = ()


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
    expected_paths: tuple[str, ...]


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


@dataclass(frozen=True)
class CombinedRenameE2ETestCase:
    description: str
    expected_declarations: tuple[str, ...]
    expected_new_columns: tuple[str, ...]
    expected_old_columns: tuple[str, ...]


@dataclass(frozen=True)
class MissingOriginE2ETestCase:
    description: str
    target_settings: str
    build_args: tuple[str, ...]
    expected_exit: int
    expected_output: str
    expected_relation_type: str | None
    expected_columns: tuple[str, ...] = ()
