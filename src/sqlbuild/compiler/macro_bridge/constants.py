"""Macro call event tags shared with the native memo, and the active bridge of a render."""

from __future__ import annotations

from contextvars import ContextVar

ACTIVE_MACRO_BRIDGE: ContextVar[object | None] = ContextVar(
    "sqlbuild_active_macro_bridge", default=None
)
STORE_MODULE_PATHS: set[str] = set()
MACRO_CALL_STORE_FILE_NAME: str = "macro-calls.bin"
MACRO_CALL_STORE_ENVIRONMENT_VERSION: str = "macro-call-store-v2"
PROJECT_ROOT_SEARCH_PATH_STAMP: int = -2
MISSING_SEARCH_PATH_STAMP: int = -1
INSTALLED_PACKAGE_DIRECTORY_NAMES: frozenset[str] = frozenset({"site-packages", "dist-packages"})
INSTALLED_DISTRIBUTION_SUFFIX: str = ".dist-info"
INSTALLED_RECORD_FILE_NAME: str = "RECORD"
INTERPRETER_MODULE_ORIGINS: frozenset[str] = frozenset({"built-in", "frozen"})
MAIN_MODULE_NAME: str = "__main__"
