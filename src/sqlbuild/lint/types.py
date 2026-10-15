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

type RelationKeyRow = tuple[
    str,
    str,
    str,
    str,
    str,
    bool,
    list[str] | None,
    list[tuple[str, list[str], bool]],
    list[tuple[str, str | None]],
]

type DiagnosticIdentity = tuple[str, str, str, str]

type NativeLintPreparationRequest = LintPreparationRequest
