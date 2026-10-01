"""Helpers for adapter relation architecture guards."""

from __future__ import annotations

import re
from pathlib import Path

SOURCE_ROOT: Path = Path(__file__).resolve().parents[6] / "src" / "sqlbuild"
_CATALOG_SQL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"information_schema", re.IGNORECASE),
    re.compile(r"[\"']\s*SHOW\s+[A-Z]"),
)


def metadata_sql_modules() -> frozenset[str]:
    """Return source modules containing INFORMATION_SCHEMA or SHOW statement text."""

    return frozenset(
        path.relative_to(SOURCE_ROOT).as_posix()
        for path in filter(_contains_catalog_sql, SOURCE_ROOT.rglob("*.py"))
    )


def _contains_catalog_sql(path: Path) -> bool:
    text: str = path.read_text(encoding="utf-8")
    return any(pattern.search(text) is not None for pattern in _CATALOG_SQL_PATTERNS)
