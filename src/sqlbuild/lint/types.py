"""Lint domain types."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sqlbuild._native import LintPreparationRequest


class LintSeverity(StrEnum):
    """Severity assigned to one lint violation."""

    FAULT = "fault"
    WARNING = "warning"


type RuleFixStatus = Literal["applied", "refused", "unavailable"]

type RelationKeys = dict[str, tuple[tuple[str, ...], ...]]

type DiagnosticIdentity = tuple[str, str, str, str]

type NativeLintPreparationRequest = LintPreparationRequest

type NativePreparedSql = tuple[str, list[tuple[str, int, int, int, int, str]], list[str]]
