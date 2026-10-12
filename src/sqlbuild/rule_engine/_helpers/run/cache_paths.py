"""Locations of the Rules caches, namespaced by compiler engine."""

from pathlib import Path

from sqlbuild.compiler.frontier.constants import (
    NATIVE_CACHE_NAMESPACE_SUFFIX,
    TARGET_DIRECTORY_NAME,
)
from sqlbuild.rule_engine.constants import (
    RULES_BULK_CACHE_DIRECTORY_NAME,
    RULES_CACHE_DIRECTORY_NAME,
)


def rules_bulk_cache_path(*, project_dir: Path, file_name: str) -> Path:
    """Return one bulk Rules cache file owned by the active compiler engine."""

    return (
        project_dir
        / TARGET_DIRECTORY_NAME
        / f"{RULES_CACHE_DIRECTORY_NAME}{NATIVE_CACHE_NAMESPACE_SUFFIX}"
        / RULES_BULK_CACHE_DIRECTORY_NAME
        / file_name
    )
