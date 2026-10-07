"""Macro call event tags shared with the native memo, and the active bridge of a render."""

from __future__ import annotations

import itertools
from contextvars import ContextVar

from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR, STAGE_CAPTURE_DIR_ENV_VAR
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
COMPILES_STARTED: itertools.count[int] = itertools.count()
MACRO_CALL_STORE_FILE_NAME: str = "macro-calls.bin"
MACRO_CALL_STORE_ENVIRONMENT_VERSION: str = "macro-call-store-v2"
VALUE_RENDERER_FIELD: str = "_value_renderer"
PROJECT_ROOT_SEARCH_PATH_STAMP: int = -2
MISSING_SEARCH_PATH_STAMP: int = -1
MODULE_DIGEST_ROW_FIELDS: int = 2
INSTALLED_PACKAGE_DIRECTORY_NAMES: frozenset[str] = frozenset({"site-packages", "dist-packages"})
INSTALLED_DISTRIBUTION_SUFFIX: str = ".dist-info"
INSTALLED_RECORD_FILE_NAME: str = "RECORD"
INTERPRETER_MODULE_ORIGINS: frozenset[str] = frozenset({"built-in", "frozen"})
STORE_TRACKED_ENVIRONMENT_PREFIXES: tuple[str, ...] = ("SQLBUILD_", "SQB_")
STORE_UNTRACKED_ENVIRONMENT_NAMES: frozenset[str] = frozenset(
    {COMPILER_ENGINE_ENV_VAR, STAGE_CAPTURE_DIR_ENV_VAR}
)
