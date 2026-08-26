"""Immutable models for validated and authored typed SQL values."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.sql_values.constants import (
    DEFAULT_MAX_SQL_VALUE_DEPTH,
    DEFAULT_MAX_SQL_VALUE_ELEMENTS,
    DEFAULT_MAX_SQL_VALUE_SIZE,
)
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


@dataclass(frozen=True)
class AuthoredSqlSet:
    """Set literal entries retained in authored order until validation."""

    values: tuple[object, ...]


@dataclass(frozen=True)
class AuthoredSqlValueCall:
    """Source-preserving representation of an authored ``constant(...)`` call."""

    arguments: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class SqlValueLimits:
    """Safety limits applied while normalizing recursively authored values."""

    max_depth: int = DEFAULT_MAX_SQL_VALUE_DEPTH
    max_elements: int = DEFAULT_MAX_SQL_VALUE_ELEMENTS
    max_size: int = DEFAULT_MAX_SQL_VALUE_SIZE
