"""Dataclass-backed native audit result integration cases."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter


@dataclass(frozen=True)
class AuditResultWriteTestCase:
    """One append-only audit result write scenario."""

    description: str
    expected_row_count: int


@dataclass(frozen=True)
class AuditResultMetaWriteTestCase:
    """One audit result write against a table that may predate the meta column."""

    description: str
    prepare: Callable[[DuckDbAdapter, Any], None]
    audit_meta_json: str | None
    expected_meta_column: bool
    expected_meta: tuple[str | None, ...]


@dataclass(frozen=True)
class AuditResultMetaUnreadableColumnsTestCase:
    """One meta write whose column read fails."""

    description: str
    expected_row_count: int
    expected_meta_column: bool
