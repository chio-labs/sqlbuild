"""Compiler engine switch, cache namespace, and stage capture constants."""

import re

from sqlbuild.compiler.frontier.types import CompilerEngine

COMPILER_ENGINE_ENV_VAR: str = "SQLBUILD_COMPILER_ENGINE"
COMPILER_ENGINE_OPTION: str = "--compiler-engine"
DEFAULT_COMPILER_ENGINE: CompilerEngine = CompilerEngine.NATIVE
COMPILER_ENGINE_VALUES: tuple[str, ...] = tuple(engine.value for engine in CompilerEngine)
NATIVE_CACHE_NAMESPACE_SUFFIX: str = "-native-v1"
TARGET_DIRECTORY_NAME: str = "target"
CACHE_DIRECTORY_NAME: str = "cache"
COMPILER_CACHE_DIRECTORY_NAME: str = "compiler"
STAGE_CAPTURE_DIR_ENV_VAR: str = "SQLBUILD_COMPILER_STAGE_CAPTURE_DIR"
STAGE_CAPTURE_SUFFIX: str = ".json"
STAGE_CAPTURE_SHARED_MARKER: str = "__shared__"
STAGE_CAPTURE_ROOT_KEY: str = "__capture__"
STAGE_CAPTURE_SHARED_NODES_KEY: str = "__shared_nodes__"
STAGE_CAPTURE_SHARED_MIN_BYTES: int = 1024
STAGE_CAPTURE_RESERVED_KEYS: frozenset[str] = frozenset(
    {STAGE_CAPTURE_SHARED_MARKER, STAGE_CAPTURE_ROOT_KEY, STAGE_CAPTURE_SHARED_NODES_KEY}
)
STAGE_CAPTURE_INVOCATION_ID_PATTERN: re.Pattern[str] = re.compile(r"\b\d{8}T\d{6}Z_[0-9a-f]{12}\b")
STAGE_CAPTURE_INVOCATION_ID_MASK: str = "<invocation-id>"
STAGE_CAPTURE_ENGINE_NAMESPACE_PATTERN: re.Pattern[str] = re.compile(r"-native-v\d+\b")
STAGE_CAPTURE_SKIPPED_SLOTS: frozenset[str] = frozenset({"__dict__", "__weakref__"})
STAGE_CAPTURE_UNORDERED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "sqlbuild.compiler.sql_analysis.classes.binding_catalog:BindingCatalog": frozenset(
        {"schemas", "analysis_shapes", "expression_shapes"}
    )
}
STAGE_CAPTURE_OMITTED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "sqlbuild.compiler.sql_analysis.classes.binding_catalog:BindingCatalog": frozenset(
        {"shared_analyses"}
    )
}
STAGE_CAPTURE_DECODED_SEQUENCES: frozenset[str] = frozenset(
    {"sqlbuild.compiler.compile.models:CompactLineageFacts"}
)
