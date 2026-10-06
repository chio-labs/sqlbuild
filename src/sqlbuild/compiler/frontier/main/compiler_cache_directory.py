"""Project-local compiler store root for the active engine."""

from pathlib import Path

from sqlbuild.compiler.frontier.constants import (
    CACHE_DIRECTORY_NAME,
    COMPILER_CACHE_DIRECTORY_NAME,
    TARGET_DIRECTORY_NAME,
)
from sqlbuild.compiler.frontier.main.engine_cache_name import engine_cache_name


def compiler_cache_directory(project_dir: Path) -> Path:
    """Return the compiler store root owned by the active engine."""

    return (
        project_dir
        / TARGET_DIRECTORY_NAME
        / CACHE_DIRECTORY_NAME
        / engine_cache_name(COMPILER_CACHE_DIRECTORY_NAME)
    )
