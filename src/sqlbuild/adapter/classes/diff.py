"""Diff mixin for adapter implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlbuild.adapter.models import (
    CursorValue,
    RowDiffResult,
    RowDiffSampleRow,
    RowDiffTolerances,
    SchemaDiffResult,
)


class DiffMixin(ABC):
    """Compares relation data across targets."""

    @abstractmethod
    def diff_schema(
        self,
        *,
        connection: Any,
        left: str,
        right: str,
    ) -> SchemaDiffResult:
        """Compare the schema of two relations."""
        ...

    @abstractmethod
    def diff_rows(
        self,
        *,
        connection: Any,
        left: str,
        right: str,
        unique_key: str | tuple[str, ...],
        excluded_columns: tuple[str, ...] = (),
        tolerances: RowDiffTolerances | None = None,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> RowDiffResult:
        """Compare row-level data between two relations."""
        ...

    @abstractmethod
    def count_rows(
        self,
        *,
        connection: Any,
        relation: str,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> int:
        """Return the row count for a relation, optionally bounded by cursor."""
        ...

    @abstractmethod
    def sample_unequal_rows(
        self,
        *,
        connection: Any,
        left: str,
        right: str,
        unique_key: str | tuple[str, ...],
        excluded_columns: tuple[str, ...] = (),
        tolerances: RowDiffTolerances | None = None,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
        limit: int = 20,
    ) -> tuple[RowDiffSampleRow, ...]:
        """Return sampled unequal rows for verbose diff output."""
        ...

    @abstractmethod
    def sample_side_only_rows(
        self,
        *,
        connection: Any,
        left: str,
        right: str,
        unique_key: str | tuple[str, ...],
        side: str,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
        limit: int = 20,
    ) -> tuple[tuple[tuple[str, object], ...], ...]:
        """Return sampled side-only keys for verbose diff output."""
        ...
