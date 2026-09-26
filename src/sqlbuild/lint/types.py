"""Lint domain types."""

from __future__ import annotations

from enum import StrEnum

type LintRelationCatalog = dict[tuple[str, str, str | None], tuple[str, ...]]


class LintSeverity(StrEnum):
    """Severity assigned to one lint violation."""

    FAULT = "fault"
    WARNING = "warning"
