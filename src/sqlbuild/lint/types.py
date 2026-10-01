"""Lint domain types."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


class LintSeverity(StrEnum):
    """Severity assigned to one lint violation."""

    FAULT = "fault"
    WARNING = "warning"


type RuleFixStatus = Literal["applied", "refused", "unavailable"]
