"""Public entry for joining several help paragraphs."""

from __future__ import annotations

from sqlbuild.errors.setting_help._helpers.text import join_helps as _join_helps


def join_helps(*helps: str) -> str:
    """Join several help paragraphs into one help text, one `= help:` label per paragraph."""

    return _join_helps(helps)
