"""Test case types for executor column rename helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverlappingColumnRenameTestCase:
    description: str
    transactional: bool
    expected_columns: tuple[str, ...]
    expected_decisions: tuple[str, ...]


@dataclass(frozen=True)
class ComposeColumnAliasesTestCase:
    description: str
    renames: tuple[tuple[str, str], ...]
    expected_aliases: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SnowflakeOldNameSqlTestCase:
    description: str
    column_aliases: tuple[tuple[str, str], ...]
    expected_statements: tuple[str, ...]
