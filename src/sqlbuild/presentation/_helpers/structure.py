"""Structural CLI vocabulary implementations (trees, phase lines, headers)."""

from __future__ import annotations

from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.constants import (
    TREE_BRANCH_GLYPH,
    TREE_LAST_GLYPH,
)


def tree_connector(*, style: CliStyle, last: bool) -> str:
    """Render a dim tree connector for a group entry."""

    return style.muted(TREE_LAST_GLYPH if last else TREE_BRANCH_GLYPH)


def format_surface_header(*, style: CliStyle, title: str, context: str | None = None) -> str:
    """Render a command surface header: accent title plus dim context."""

    rendered: str = style.title(title)
    if context:
        rendered = f"{rendered}  {style.muted(context)}"
    return rendered
