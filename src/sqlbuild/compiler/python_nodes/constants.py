"""Python-node selector constants."""

from __future__ import annotations

EMPTY_SELECTOR_FOLDER: str = ""
SQL_MODEL_PATH_ROOT: str = "models"
PYTHON_NODE_PATH_ROOTS: frozenset[str] = frozenset({"tasks", "assets", "checks", "loaders"})
UNIFIED_PATH_ROOTS: frozenset[str] = frozenset({*PYTHON_NODE_PATH_ROOTS, SQL_MODEL_PATH_ROOT})
TAG_NOT_FOUND_ERROR_CODE: str = "S008"
