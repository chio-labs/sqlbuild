"""Cheap source scan for contract-aware fixture formatting candidates."""

from __future__ import annotations

import re
from pathlib import Path

_FIXTURE_TYPED_NULL_PATTERN: re.Pattern[str] = re.compile(
    r"(?:CAST\s*\(\s*NULL\s+AS\b|NULL\s*::)", re.IGNORECASE
)
_FIXTURE_CTE_MARKERS: tuple[str, ...] = ("__ref__", "__source__", "__seed__")
_IGNORED_SEARCH_DIRECTORIES: frozenset[str] = frozenset({".git", ".venv", "target", "node_modules"})


def has_fixture_typed_null_candidates(*, project_dir: Path) -> bool:
    """Return whether source files may contain safe fixture-null autofixes."""

    for file_path in project_dir.rglob("*.sql"):
        if any(part in _IGNORED_SEARCH_DIRECTORIES for part in file_path.parts):
            continue
        try:
            contents: str = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        folded: str = contents.casefold()
        if not any(marker in folded for marker in _FIXTURE_CTE_MARKERS):
            continue
        if _FIXTURE_TYPED_NULL_PATTERN.search(contents) is not None:
            return True
    return False
