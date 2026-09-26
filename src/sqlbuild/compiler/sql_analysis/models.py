"""Stable SQLBuild-owned schema validation models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SqlBindingDiagnostic:
    """One native binding error or non-blocking runtime-conversion warning."""

    code: str
    message: str
    line: int | None = None
    column: int | None = None
    start: int | None = None
    end: int | None = None
    severity: str = "error"


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
    known_functions: tuple[str, ...] = ()
    known_types: tuple[str, ...] = ()
    quoted_identifiers_ignore_case: bool = False
    catalog: Any | None = field(default=None, repr=False, compare=False)
