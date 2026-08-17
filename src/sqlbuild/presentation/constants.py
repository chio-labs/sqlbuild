"""Presentation constants."""

from __future__ import annotations

DEFAULT_MAX_DISPLAY_ENTRIES: int = 20
ERROR_STATUS_LABELS: frozenset[str] = frozenset({"ERROR", "FAIL", "FAILED"})
PHASE_FAIL_GLYPH: str = "\u2717"
PHASE_OK_GLYPH: str = "\u2713"
PROGRESS_DISABLED_VALUES: frozenset[str] = frozenset({"1", "on", "true", "yes"})
SKIPPED_STATUS_LABELS: frozenset[str] = frozenset({"SKIP", "SKIPPED"})
SUCCESS_STATUS_LABELS: frozenset[str] = frozenset({"OK", "PASS", "SUCCESS"})
TREE_BRANCH_GLYPH: str = "\u251c\u2500\u2500"
TREE_LAST_GLYPH: str = "\u2514\u2500\u2500"
TREE_PIPE_GLYPH: str = "\u2502"
WARNING_STATUS_LABELS: frozenset[str] = frozenset({"WARN", "WARNING"})
