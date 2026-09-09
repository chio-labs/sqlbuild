"""Lint domain types."""

from __future__ import annotations

from enum import StrEnum


class LintSeverity(StrEnum):
    """Severity assigned to one lint violation."""

    FAULT = "fault"
    WARNING = "warning"
