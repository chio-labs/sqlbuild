"""Lint domain types."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlbuild.lint.models import CustomLintFinding


type CustomLintCheck = Callable[..., Iterable[CustomLintFinding]]


class LintSeverity(StrEnum):
    """Severity assigned to one lint violation."""

    FAULT = "fault"
    WARNING = "warning"
