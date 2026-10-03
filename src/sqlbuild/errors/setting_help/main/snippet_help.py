"""Public entry for help that shows an exact authored snippet to add."""

from __future__ import annotations

from sqlbuild.errors.setting_help._helpers.text import snippet_help as _snippet_help


def snippet_help(*, purpose: str, target: str, lines: tuple[str, ...]) -> str:
    """Render `<purpose>, <target>:` followed by the exact lines to write, one per line."""

    return _snippet_help(purpose=purpose, target=target, lines=lines)
