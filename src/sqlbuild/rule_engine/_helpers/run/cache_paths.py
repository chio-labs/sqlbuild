"""Locations of the Rules caches, namespaced by compiler engine."""

from pathlib import Path

from sqlbuild.compiler.frontier.constants import TARGET_DIRECTORY_NAME
from sqlbuild.compiler.frontier.main.engine_cache_name import engine_cache_name
from sqlbuild.rule_engine.constants import (
    RULES_BULK_CACHE_DIRECTORY_NAME,
    RULES_CACHE_DIRECTORY_NAME,
)


def rules_bulk_cache_path(*, project_dir: Path, file_name: str) -> Path:
    """Return one bulk Rules cache file owned by the active compiler engine."""

    return (
        project_dir
        / TARGET_DIRECTORY_NAME
        / engine_cache_name(RULES_CACHE_DIRECTORY_NAME)
        / RULES_BULK_CACHE_DIRECTORY_NAME
        / file_name
    )
