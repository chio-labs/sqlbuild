"""Strict adapter requiring full implementation of every method."""

from __future__ import annotations

from abc import abstractmethod

from sqlbuild.adapter.shared.classes.connection import ConnectionMixin
from sqlbuild.adapter.shared.classes.diff import DiffMixin
from sqlbuild.adapter.shared.classes.materialization import MaterializationMixin
from sqlbuild.adapter.shared.classes.schema import SchemaMixin
from sqlbuild.adapter.shared.types import FrameworkType


class StrictAdapter(
    ConnectionMixin,
    SchemaMixin,
    MaterializationMixin,
    DiffMixin,
):
    """All-abstract adapter interface.

    Subclass this to be forced to implement every adapter method explicitly.
    The concrete defaults from ConnectionMixin (begin, commit, rollback,
    transaction, supports_transactions) are inherited but may be overridden.
    """

    @abstractmethod
    def default_schema(self) -> str | None:
        """Return the adapter's default schema name, or None if schema is required."""
        ...

    @abstractmethod
    def default_database(self) -> str | None:
        """Return the adapter's default database name, or None if database is required."""
        ...

    @abstractmethod
    def star_exclude_keyword(self) -> str:
        """Return the SQL keyword for SELECT * EXCLUDE/EXCEPT syntax."""
        ...

    @abstractmethod
    def render_qualified_name(
        self,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> str | None:
        """Render a fully qualified relation name for this adapter."""
        ...

    @abstractmethod
    def render_framework_type(self, type_name: FrameworkType) -> str:
        """Render one framework-internal logical type for this adapter."""
        ...

    @abstractmethod
    def render_set_difference_operator(self) -> str:
        """Render the set-difference operator keyword for this adapter."""
        ...

    @abstractmethod
    def sqlglot_dialect(self) -> str | None:
        """Return the SQLGlot dialect name for this adapter, if any."""
        ...

    @abstractmethod
    def render_cursor_bound_literal(self, value: str, cursor_type: str | None) -> str:
        """Render one cursor bound literal for this adapter and cursor type."""
        ...

    @abstractmethod
    def default_table_promotion_mode(self) -> str:
        """Return the adapter default table promotion mode."""
        ...
