"""Render actionable authored-source lint diagnostics."""

from __future__ import annotations

import textwrap
from pathlib import Path

from rich.cells import cell_len

from sqlbuild.lint.constants import TAB_CHARACTER, VIOLATION_SEVERITY_FAULT
from sqlbuild.lint.models import LintRunResult, LintViolation
from sqlbuild.presentation.classes.cli_style import CliStyle

_REPORT_LINE_WIDTH: int = 100
_HELP_PREFIX: str = "  = help: "
_HELP_CONTINUATION: str = "          "


def format_lint_diagnostics(
    *, result: LintRunResult, root: Path, use_color: bool
) -> tuple[str, ...]:
    """Format every lint violation as a source-pointing diagnostic block."""

    style: CliStyle = CliStyle(use_color=use_color)
    return tuple(
        _format_violation(violation=violation, result=result, root=root, style=style)
        for violation in result.violations
    )


def _format_violation(
    *, violation: LintViolation, result: LintRunResult, root: Path, style: CliStyle
) -> str:
    severity: str = "error" if violation.severity == VIOLATION_SEVERITY_FAULT else "warning"
    label: str = f"{severity}[{violation.code}]"
    styled_label: str = (
        style.error_strong(label)
        if violation.severity == VIOLATION_SEVERITY_FAULT
        else style.warning_strong(label)
    )
    location: str = (
        f"{_display_path(path=violation.file_path, root=root)}:{violation.line}:{violation.column}"
    )
    lines: list[str] = [
        f"{styled_label}: {violation.message}",
        style.muted(f" --> {location}"),
    ]
    source_text: str | None = result.source_texts.get(violation.file_path)
    if source_text is not None:
        source_lines: list[str] = source_text.splitlines()
        if 1 <= violation.line <= len(source_lines):
            lines.extend(
                _source_excerpt(
                    violation=violation,
                    source_line=source_lines[violation.line - 1],
                    style=style,
                )
            )
    if violation.remediation is not None:
        lines.extend(_help_lines(remediation=violation.remediation, style=style))
    return "\n".join(lines)


def _source_excerpt(
    *, violation: LintViolation, source_line: str, style: CliStyle
) -> tuple[str, ...]:
    line_number: str = str(violation.line)
    gutter: str = " " * len(line_number)
    start_index: int = min(max(violation.column - 1, 0), len(source_line))
    end_index: int = _excerpt_end_index(
        violation=violation,
        source_line=source_line,
        start_index=start_index,
    )
    padding: str = _display_padding(source_line[:start_index])
    caret_count: int = max(1, cell_len(source_line[start_index:end_index]))
    caret: str = "^" * caret_count
    styled_caret: str = (
        style.error_strong(caret)
        if violation.severity == VIOLATION_SEVERITY_FAULT
        else style.warning_strong(caret)
    )
    return (
        style.muted(f"{gutter} |"),
        f"{style.muted(f'{line_number} |')} {source_line}",
        f"{style.muted(f'{gutter} |')} {padding}{styled_caret}",
        style.muted(f"{gutter} |"),
    )


def _excerpt_end_index(*, violation: LintViolation, source_line: str, start_index: int) -> int:
    if violation.end_line == violation.line and violation.end_column is not None:
        return min(max(violation.end_column - 1, start_index + 1), len(source_line))
    if violation.end_line is not None and violation.end_line != violation.line:
        return len(source_line)
    return min(start_index + 1, len(source_line))


def _display_padding(prefix: str) -> str:
    return "".join(
        TAB_CHARACTER if character == TAB_CHARACTER else " " * cell_len(character)
        for character in prefix
    )


def _help_lines(*, remediation: str, style: CliStyle) -> tuple[str, ...]:
    wrapped: list[str] = textwrap.wrap(
        remediation,
        width=_REPORT_LINE_WIDTH,
        initial_indent=_HELP_PREFIX,
        subsequent_indent=_HELP_CONTINUATION,
    )
    if not wrapped:
        return ()
    first: str = wrapped[0].removeprefix(_HELP_PREFIX)
    return (f"  {style.muted('= help:')} {first}", *wrapped[1:])


def _display_path(*, path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
