"""Public entry for help that shows an exact MODEL header entry."""

from __future__ import annotations

from sqlbuild.errors.setting_help._helpers.text import model_header_help as _model_header_help


def model_header_help(*, purpose: str, entry: str, follow_up: str | None = None) -> str:
    """Render `<purpose>, add this to the MODEL header:` followed by the exact header entry."""

    return _model_header_help(purpose=purpose, entry=entry, follow_up=follow_up)
