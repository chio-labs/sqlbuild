"""Constants for the lint and format layer."""

from __future__ import annotations

from sqlbuild.lint.types import LintSeverity

VIOLATION_SEVERITY_FAULT: LintSeverity = LintSeverity.FAULT
VIOLATION_SEVERITY_WARNING: LintSeverity = LintSeverity.WARNING

DEFAULT_MAX_LITERAL_LENGTH: int = 100
DEFAULT_MAX_RANKING_ORDER_BY: int = 5
