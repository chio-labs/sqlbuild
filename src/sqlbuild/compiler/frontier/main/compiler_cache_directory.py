"""Project-local compiler store root."""

from pathlib import Path

from sqlbuild.compiler.frontier.constants import (
    CACHE_DIRECTORY_NAME,
    COMPILER_CACHE_DIRECTORY_NAME,
    NATIVE_CACHE_NAMESPACE_SUFFIX,
    TARGET_DIRECTORY_NAME,
)


def compiler_cache_directory(project_dir: Path) -> Path:
    """Return the project's compiler store root."""

    return (
        project_dir
        / TARGET_DIRECTORY_NAME
        / CACHE_DIRECTORY_NAME
        / f"{COMPILER_CACHE_DIRECTORY_NAME}{NATIVE_CACHE_NAMESPACE_SUFFIX}"
    )
