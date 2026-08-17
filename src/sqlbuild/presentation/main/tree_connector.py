"""Public tree connector rendering entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.structure import tree_connector as _tree_connector
from sqlbuild.presentation.classes.cli_style import CliStyle


def tree_connector(*, style: CliStyle, last: bool) -> str:
    """Render a dim tree connector for a group entry."""

    return _tree_connector(style=style, last=last)
