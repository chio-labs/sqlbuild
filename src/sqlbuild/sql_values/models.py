"""Immutable models for validated and authored typed SQL values."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.sql_values.types import SqlValueKind, SqlValuePayload


@dataclass(frozen=True)
class SqlLogicalType:
    """Logical type inferred for a normalized SQL value."""

    kind: SqlValueKind
    element_type: SqlLogicalType | None = None

    @property
    def display_name(self) -> str:
        """Return a stable human-readable type name."""

        if self.element_type is None:
            return self.kind.value
        return f"{self.kind.value}<{self.element_type.display_name}>"


@dataclass(frozen=True)
class SqlValue:
    """One validated, canonical SQL value."""

    logical_type: SqlLogicalType
    value: SqlValuePayload

    @property
    def kind(self) -> SqlValueKind:
        """Return the outer logical kind."""

        return self.logical_type.kind
