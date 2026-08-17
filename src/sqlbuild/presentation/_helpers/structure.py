"""Structural CLI vocabulary implementations (trees, phase lines, headers)."""

from __future__ import annotations

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
