"""Lineage helper constants."""

from __future__ import annotations

from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.planner.types import SelectorKind

COLUMN_LINEAGE_MODE_VALUES: tuple[str, ...] = tuple(mode.value for mode in ColumnLineageMode)
RICH_LINEAGE_STATUS_MODEL_THRESHOLD: int = 100
UNLIMITED_DEPTH_VALUE: str = "all"
UPSTREAM_DIRECTION: str = "upstream"
DOWNSTREAM_DIRECTION: str = "downstream"
BOTH_DIRECTIONS: str = "both"
JSON_OUTPUT_FORMAT: str = "json"
LIST_OUTPUT_FORMAT: str = "list"
SQL_FILE_SUFFIX: str = ".sql"
SELECTOR_INTERSECTION_MARKER: str = ","
PATH_BETWEEN_MARKER: str = "~"
SELECTOR_KIND_SEPARATOR: str = ":"
PATH_SEPARATOR: str = "/"
SELECTOR_EXPANSION_MARKER: str = "+"
COLUMN_TARGET_SEPARATOR: str = "."
SUPPORTED_TYPED_SELECTOR_KINDS: frozenset[str] = frozenset(
    {
        SelectorKind.SEED,
        SelectorKind.SOURCE,
        SelectorKind.TAG,
        SelectorKind.PATH,
    }
)
