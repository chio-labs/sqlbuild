"""Compiler engine switch, cache namespace, and stage capture constants."""

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
STAGE_CAPTURE_SKIPPED_SLOTS: frozenset[str] = frozenset({"__dict__", "__weakref__"})
STAGE_CAPTURE_UNORDERED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "sqlbuild.compiler.sql_analysis.classes.binding_catalog:BindingCatalog": frozenset(
        {"schemas", "analysis_shapes", "expression_shapes", "shared_analyses"}
    )
}
