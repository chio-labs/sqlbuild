"""Public counted section header style entry."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.presentation._helpers.structure import count_header_style as _count_header_style
from sqlbuild.presentation.classes.cli_style import CliStyle


def count_header_style(
    *, style: CliStyle, title_style: Callable[[str], str] | None = None
) -> Callable[[str], str]:
    """Return a header style that renders ``Title (count)`` as a bold title and dim count."""

    return _count_header_style(style=style, title_style=title_style)
