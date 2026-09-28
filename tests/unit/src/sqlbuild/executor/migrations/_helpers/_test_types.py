"""Test case types for executor column rename helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationGrant


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
class AdapterOldNameSqlTestCase:
    description: str
    adapter: BaseAdapter
    database: str | None
    column_aliases: tuple[tuple[str, str], ...]
    expected_statements: tuple[str, ...]
    expected_state_table_prefix: str
    expected_transactional: bool


@dataclass(frozen=True)
class ReaderAccessWarningTestCase:
    description: str
    adapter: BaseAdapter
    grants: tuple[RelationGrant, ...]
    expected_warnings: tuple[str, ...]


@dataclass(frozen=True)
class GrantReconcileTestCase:
    description: str
    adapter: BaseAdapter
    current: tuple[RelationGrant, ...]
    target: tuple[RelationGrant, ...]
    expected_statements: tuple[str, ...]
