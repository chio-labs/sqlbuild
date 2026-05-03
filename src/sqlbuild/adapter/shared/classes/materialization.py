"""Materialization mixin for adapter implementations."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo


class MaterializationMixin:
    """Executes SQL materialization operations against the warehouse."""

    @abstractmethod
    def create_table_as(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Create or replace a table from a SELECT statement."""
        ...

    @abstractmethod
    def create_view_as(self, connection: Any, *, target: str, sql: str) -> None:
        """Create or replace a view from a SELECT statement."""
        ...

    @abstractmethod
    def drop(self, connection: Any, *, target: str, if_exists: bool = True) -> None:
        """Drop a relation from the warehouse."""
        ...

    @abstractmethod
    def rename(self, connection: Any, *, source: str, target: str) -> None:
        """Rename a relation."""
        ...

    @abstractmethod
    def swap(self, connection: Any, *, left: str, right: str) -> None:
        """Swap two relations atomically where supported."""
        ...

    @abstractmethod
    def clone(
        self,
        connection: Any,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> None:
        """Clone a relation using zero-copy where supported."""
        ...

    @abstractmethod
    def load_seed(
        self,
        connection: Any,
        *,
        target: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        replace: bool = True,
        infer_types: bool = False,
    ) -> None:
        """Load a seed CSV file into a warehouse table."""
        ...

    @abstractmethod
    def append(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        columns: tuple[str, ...] | None = None,
    ) -> None:
        """Insert rows from a SELECT statement into an existing table."""
        ...

    @abstractmethod
    def delete_insert(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        columns: tuple[str, ...] | None = None,
    ) -> None:
        """Delete matching rows then insert from a SELECT statement."""
        ...

    @abstractmethod
    def merge(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
    ) -> None:
        """Upsert rows from a SELECT statement using MERGE or equivalent."""
        ...

    @abstractmethod
    def add_columns(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
    ) -> None:
        """Add columns to an existing table."""
        ...

    @abstractmethod
    def drop_columns(
        self,
        connection: Any,
        *,
        target: str,
        column_names: tuple[str, ...],
    ) -> None:
        """Drop columns from an existing table."""
        ...

    @abstractmethod
    def alter_column_types(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
    ) -> None:
        """Alter column types on an existing table."""
        ...
