"""Structural CLI vocabulary implementations (trees, phase lines, headers)."""

from __future__ import annotations

from sqlbuild.presentation.classes.cli_style import CliStyle

TREE_BRANCH_GLYPH: str = "├──"
TREE_LAST_GLYPH: str = "└──"
TREE_PIPE_GLYPH: str = "│"
PHASE_OK_GLYPH: str = "✓"
PHASE_FAIL_GLYPH: str = "✗"


def tree_branch(*, style: CliStyle) -> str:
    """Render a dim mid-branch tree connector."""

    return style.muted(TREE_BRANCH_GLYPH)


def tree_last(*, style: CliStyle) -> str:
    """Render a dim final-branch tree connector."""

    return style.muted(TREE_LAST_GLYPH)


def tree_pipe(*, style: CliStyle) -> str:
    """Render a dim vertical tree connector."""

    return style.muted(TREE_PIPE_GLYPH)


def tree_connector(*, style: CliStyle, last: bool) -> str:
    """Render a dim tree connector for a group entry."""

    return tree_last(style=style) if last else tree_branch(style=style)


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


def format_tree_leaf(
    *,
    style: CliStyle,
    key: str,
    value: str,
    last: bool,
    indent: str = "    ",
    key_width: int = 0,
) -> str:
    """Render a dim-keyed tree leaf with a plain value."""

    connector: str = tree_connector(style=style, last=last)
    padded_key: str = f"{key:<{key_width}}" if key_width else key
    return f"{indent}{connector} {style.muted(padded_key)}  {value}"


def format_rollup_line(*, style: CliStyle, text: str) -> str:
    """Render a dim rollup note for routine work omitted from detailed groups."""

    return f"{tree_pipe(style=style)} {style.muted(text)}"


def format_status_cell(*, style: CliStyle, status: str, width: int = 6) -> str:
    """Render a fixed-width status cell padded on the plain text, not the ANSI text."""

    padding: str = " " * max(0, width - len(status))
    return f"{style.status(status=status)}{padding}"


def format_completion_line(
    *, style: CliStyle, state: str, label: str, summary: str | None = None
) -> str:
    """Render a single-line completion summary: state glyph, label, trailing summary."""

    if state == "fail":
        glyph: str = style.error(PHASE_FAIL_GLYPH)
        rendered_label: str = style.error_strong(label)
    elif state == "warn":
        glyph = style.warning(PHASE_OK_GLYPH)
        rendered_label = style.warning_strong(label)
    else:
        glyph = style.success(PHASE_OK_GLYPH)
        rendered_label = label
    rendered: str = f"{glyph} {rendered_label}"
    if summary:
        rendered = f"{rendered}  {summary}"
    return rendered
