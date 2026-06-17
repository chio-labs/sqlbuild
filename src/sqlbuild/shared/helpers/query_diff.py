"""Unified SQL/text diff formatting helpers."""

from __future__ import annotations

import difflib

from sqlbuild.shared.helpers.cli_style import CliStyle


def format_query_diff(previous: str, current: str) -> list[str]:
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
        if stripped.startswith("+") and not stripped.startswith("+++"):
            result.append(style.success(formatted))
        elif stripped.startswith("-") and not stripped.startswith("---"):
            result.append(style.error(formatted))
        elif stripped.startswith(("---", "+++", "@@")):
            result.append(style.muted(formatted))
        else:
            result.append(formatted)
    return result
