"""Stable constants for typed SQL resource references."""

from collections.abc import Callable
from contextvars import ContextVar

RELATION_RENDERER: ContextVar[Callable[[object], str] | None] = ContextVar(
    "sqlbuild_relation_renderer", default=None
)
