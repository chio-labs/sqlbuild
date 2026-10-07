"""Macro call event tags shared with the native memo, and the active bridge of a render."""

from __future__ import annotations

from contextvars import ContextVar

from sqlbuild.compiler.references.types import SqlReferenceKind

MACRO_USE_EVENT: int = 0
DECLARATION_READ_EVENT: int = 1
GENERATED_SQL_EVENT: int = 2
ARGUMENT_REFERENCE_EVENT: int = 3
GENERATED_REFERENCE_MARKERS: tuple[str, ...] = tuple(
    f"{kind.function_name}(" for kind in SqlReferenceKind
)
ACTIVE_MACRO_BRIDGE: ContextVar[object | None] = ContextVar(
    "sqlbuild_active_macro_bridge", default=None
)
