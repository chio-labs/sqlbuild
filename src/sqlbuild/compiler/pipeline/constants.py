"""Compiler pipeline decision constants."""

from __future__ import annotations

DEFERRED_TARGET_CONTEXT_KEYS: frozenset[str] = frozenset({"schema", "database"})
MODEL_PATH_ROOT: str = "models"
PATH_SELECTOR_PREFIX: str = "path:"
PATH_SEPARATORS: frozenset[str] = frozenset({"/", "\\"})
