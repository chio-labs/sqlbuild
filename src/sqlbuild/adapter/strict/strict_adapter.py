"""Strict adapter requiring full implementation of every method."""

from __future__ import annotations

from abc import abstractmethod

from sqlbuild.adapter.shared.classes.connection import ConnectionMixin
from sqlbuild.adapter.shared.classes.diff import DiffMixin
from sqlbuild.adapter.shared.classes.materialization import MaterializationMixin
from sqlbuild.adapter.shared.classes.schema import SchemaMixin


class StrictAdapter(
    ConnectionMixin,
    SchemaMixin,
    MaterializationMixin,
    DiffMixin,
):
    """All-abstract adapter interface.

    Subclass this to be forced to implement every adapter method explicitly.
    The concrete defaults from ConnectionMixin (begin, commit, rollback,
    run_in_transaction, supports_transactions) are inherited but may be
    overridden.
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
