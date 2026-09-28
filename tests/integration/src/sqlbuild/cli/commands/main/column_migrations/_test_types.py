"""Test case types for column migration integration tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass(frozen=True)
class ColumnRenameOutcomeTestCase:
    description: str
    renamed_sql: str
    expected_planned: tuple[tuple[str, str, str, str], ...]
    expected_plan_fragment: str
    expected_columns: tuple[str, ...]
    expected_values: tuple[tuple[int, Any], ...]
    expected_events: tuple[tuple[str, str, str, str], ...]
    value_column: str = "revenue"


@dataclass(frozen=True)
class CompletedColumnRenameTestCase:
    description: str
    renamed_sql: str
    expected_planned: tuple[tuple[str, str, str, str], ...]
    expected_notice: str
    expected_final_line: str


@dataclass(frozen=True)
class NearMatchPolicyTestCase:
    description: str
    renamed_sql: str
    expected_hint: str
    expected_columns: tuple[str, ...]


@dataclass(frozen=True)
class RenameWithPolicyTestCase:
    description: str
    renamed_sql: str
    expected_columns: tuple[str, ...]
    expected_values: tuple[tuple[int, Any], ...]
    added_column: str = "revenue"
    expected_added_values: tuple[tuple[int, Any], ...] = (
        (1, 101),
        (2, 102),
        (3, 103),
        (4, 104),
        (5, 105),
    )


@dataclass(frozen=True)
class ColumnRenameRecoveryTestCase:
    description: str
    renamed_sql: str
    install_failure: Callable[[pytest.MonkeyPatch], None]
    expected_retry_planned: tuple[tuple[str, str, str, str], ...]
    expected_events: tuple[tuple[str, str, str, str], ...]
    expected_values: tuple[tuple[int, Any], ...]


@dataclass(frozen=True)
class BlockedColumnRenameTestCase:
    description: str
    renamed_sql: str
    expected_decision: str
    expected_error: str
    prepare_sql: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ColumnMigrationCompileErrorTestCase:
    description: str
    model_sql: str
    expected_fragment: str


@dataclass(frozen=True)
class SnapshotColumnRenameTestCase:
    description: str
    renamed_sql: str
    expected_planned: tuple[tuple[str, str, str, str], ...]
    expected_values: tuple[tuple[int, Any], ...]


@dataclass(frozen=True)
class CursorColumnRenameTestCase:
    description: str
    renamed_sql: str
    expected_planned: tuple[tuple[str, str, str, str], ...]
    expected_order_ids: tuple[int, ...]


@dataclass(frozen=True)
class FirstRunDeclarationTestCase:
    description: str
    model_sql: str
    expected_planned: tuple[tuple[str, str, str, str], ...]
    expected_columns: tuple[str, ...]
