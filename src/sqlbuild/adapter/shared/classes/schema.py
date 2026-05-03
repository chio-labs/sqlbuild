"""Schema inspection mixin for adapter implementations."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo


class SchemaMixin:
    """Inspects warehouse schema and relation metadata."""

    @abstractmethod
    def list_relations(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
    ) -> tuple[RelationInfo, ...]:
        """Return all relations in the given database/schema scope."""
        ...

    @abstractmethod
    def get_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> tuple[ColumnInfo, ...]:
        """Return column metadata for a single relation."""
        ...

    @abstractmethod
    def get_all_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        """Return column metadata for all relations in the given scope."""
        ...

    @abstractmethod
    def relation_exists(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        """Return whether the named relation exists in the warehouse."""
        ...
