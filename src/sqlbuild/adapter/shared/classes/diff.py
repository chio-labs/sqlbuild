"""Diff mixin for adapter implementations."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from sqlbuild.adapter.shared.models import CursorValue, RowDiffResult, SchemaDiffResult


class DiffMixin:
    """Compares relation data across environments."""

    @abstractmethod
    def diff_schema(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
    ) -> SchemaDiffResult:
        """Compare the schema of two relations."""
        ...

    @abstractmethod
    def diff_rows(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
        unique_key: str | tuple[str, ...],
        excluded_columns: tuple[str, ...] = (),
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> RowDiffResult:
        """Compare row-level data between two relations."""
        ...

    @abstractmethod
    def count_rows(
        self,
        connection: Any,
        *,
        relation: str,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> int:
        """Return the row count for a relation, optionally bounded by cursor."""
        ...
