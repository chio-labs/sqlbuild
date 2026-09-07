"""Stable SQLBuild-owned schema validation models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class SqlBindingDiagnostic:
    """One proven SQL binding failure returned by the native validator."""

    code: str
    message: str
    line: int | None = None
    column: int | None = None
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class SqlBindingResult:
    """Stable result of schema-aware semantic SQL validation."""

    diagnostics: tuple[SqlBindingDiagnostic, ...] = ()


@dataclass(frozen=True)
class SqlSchemaValidationRequest:
    """One expanded SQL query and its complete relation schemas."""

    sql: str
    dialect: str | None
    schema: Mapping[str, Mapping[str, str]]
