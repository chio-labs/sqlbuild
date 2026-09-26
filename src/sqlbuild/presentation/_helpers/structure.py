"""Structural CLI vocabulary implementations (trees, phase lines, headers)."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.constants import (
    PHASE_FAIL_GLYPH,
    PHASE_OK_GLYPH,
    TREE_BRANCH_GLYPH,
    TREE_LAST_GLYPH,
)
from sqlbuild.presentation.types import CompletionState


def tree_connector(*, style: CliStyle, last: bool) -> str:
    """Render a dim tree connector for a group entry."""

    return style.muted(TREE_LAST_GLYPH if last else TREE_BRANCH_GLYPH)


def format_surface_header(*, style: CliStyle, title: str, context: str | None = None) -> str:
    """Render a command surface header: accent title plus dim context."""

    rendered: str = style.title(title)
    if context:
        rendered = f"{rendered}  {style.muted(context)}"
    return rendered


def count_header_style(
    *, style: CliStyle, title_style: Callable[[str], str] | None = None
) -> Callable[[str], str]:
    """Return a header style that renders ``Title (count)`` as a bold title and dim count."""

    resolved_title_style: Callable[[str], str] = title_style or style.section

    def render(text: str) -> str:
        title, separator, count = text.rpartition(" (")
        if not separator or not text.endswith(")"):
            return resolved_title_style(text)
        return f"{resolved_title_style(title)} {style.muted(f'({count}')}"

    return render


def format_count_noun(*, count: int, singular: str, plural: str | None = None) -> str:
    """Render a count with the singular noun for one and the plural noun otherwise."""

    noun: str = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"


def format_phase_line(*, style: CliStyle, ok: bool, label: str, summary: str | None = None) -> str:
    """Render a concise phase-completion line: state glyph, label, dim summary."""

    glyph: str = style.success(PHASE_OK_GLYPH) if ok else style.error(PHASE_FAIL_GLYPH)
    rendered_label: str = label if ok else style.error_strong(label)
    rendered: str = f"{glyph} {rendered_label}"
    if summary:
        rendered = f"{rendered}  {style.muted(summary)}"
    return rendered


def format_status_cell(*, style: CliStyle, status: str, width: int = 6) -> str:
    """Render a fixed-width status cell padded on the plain text, not the ANSI text."""

    padding: str = " " * max(0, width - len(status))
    return f"{style.status(status=status)}{padding}"


def format_completion_line(
    *, style: CliStyle, state: CompletionState, label: str, summary: str | None = None
) -> str:
    """Render a single-line completion summary: state glyph, label, trailing summary."""

    if state == CompletionState.FAIL:
        glyph: str = style.error(PHASE_FAIL_GLYPH)
        rendered_label: str = style.error_strong(label)
    elif state == CompletionState.WARN:
        glyph = style.warning(PHASE_OK_GLYPH)
        rendered_label = style.warning_strong(label)
    else:
        glyph = style.success(PHASE_OK_GLYPH)
        rendered_label = label
    rendered: str = f"{glyph} {rendered_label}"
    if summary:
        rendered = f"{rendered}  {summary}"
    return rendered
