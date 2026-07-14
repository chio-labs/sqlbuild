"""Public SQL/text diff formatting entrypoint."""

from __future__ import annotations

import difflib

from sqlbuild.compiler.planner.constants import (
    UNIFIED_DIFF_ADDITION_HEADER_PREFIX,
    UNIFIED_DIFF_ADDITION_PREFIX,
    UNIFIED_DIFF_REMOVAL_HEADER_PREFIX,
    UNIFIED_DIFF_REMOVAL_PREFIX,
)
from sqlbuild.presentation.classes.cli_style import CliStyle


def format_query_diff(*, previous: str, current: str) -> list[str]:
    """Format a unified diff between previous and current SQL/text."""

    style: CliStyle = CliStyle(use_color=True)
    previous_lines: list[str] = previous.splitlines(keepends=True)
    current_lines: list[str] = current.splitlines(keepends=True)
    diff_lines: list[str] = list(
        difflib.unified_diff(previous_lines, current_lines, fromfile="previous", tofile="current")
    )
    result: list[str] = []
    line: str
    for line in diff_lines:
        stripped: str = line.rstrip("\n")
        formatted: str = f"      {stripped}"
        if (
            stripped[:1] == UNIFIED_DIFF_ADDITION_PREFIX
            and stripped[:3] != UNIFIED_DIFF_ADDITION_HEADER_PREFIX
        ):
            result.append(style.success(formatted))
        elif (
            stripped[:1] == UNIFIED_DIFF_REMOVAL_PREFIX
            and stripped[:3] != UNIFIED_DIFF_REMOVAL_HEADER_PREFIX
        ):
            result.append(style.error(formatted))
        elif stripped.startswith(("---", "+++", "@@")):
            result.append(style.muted(formatted))
        else:
            result.append(formatted)
    return result
