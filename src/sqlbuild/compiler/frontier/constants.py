"""Compiler cache namespace and stage capture constants."""

NATIVE_CACHE_NAMESPACE_SUFFIX: str = "-native-v1"
RETIRED_CACHE_NAMESPACE_SUFFIXES: tuple[str, ...] = (
    "",
    NATIVE_CACHE_NAMESPACE_SUFFIX,
    "-native-preview-v1",
)
TARGET_DIRECTORY_NAME: str = "target"
CACHE_DIRECTORY_NAME: str = "cache"
COMPILER_CACHE_DIRECTORY_NAME: str = "compiler"
STAGE_CAPTURE_DIR_ENV_VAR: str = "SQLBUILD_COMPILER_STAGE_CAPTURE_DIR"
COMPILE_REUSE_DISABLE_ENV_VAR: str = "SQLBUILD_DISABLE_COMPILE_REUSE"
STAGE_CAPTURE_SUFFIX: str = ".json"
STAGE_CAPTURE_SHARED_MARKER: str = "__shared__"
STAGE_CAPTURE_ROOT_KEY: str = "__capture__"
STAGE_CAPTURE_SHARED_NODES_KEY: str = "__shared_nodes__"
