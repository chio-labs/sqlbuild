"""Strict adapter requiring full implementation of every method."""

from __future__ import annotations

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
