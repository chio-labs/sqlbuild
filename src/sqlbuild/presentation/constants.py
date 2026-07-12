"""Presentation constants."""

from __future__ import annotations

DEFAULT_MAX_DISPLAY_ENTRIES: int = 20
ERROR_STATUS_LABELS: frozenset[str] = frozenset({"ERROR", "FAIL", "FAILED"})
PROGRESS_DISABLED_VALUES: frozenset[str] = frozenset({"1", "on", "true", "yes"})
SKIPPED_STATUS_LABELS: frozenset[str] = frozenset({"SKIP", "SKIPPED"})
SUCCESS_STATUS_LABELS: frozenset[str] = frozenset({"OK", "PASS", "SUCCESS"})
WARNING_STATUS_LABELS: frozenset[str] = frozenset({"WARN", "WARNING"})
