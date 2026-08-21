"""Preserve authored newline conventions when rewriting SQL files."""

from __future__ import annotations

from sqlbuild.lint.constants import CARRIAGE_RETURN_LINE_FEED, LINE_FEED


def newline_style(*, contents: str) -> str:
    """Return the newline convention used by the authored contents."""

    return CARRIAGE_RETURN_LINE_FEED if CARRIAGE_RETURN_LINE_FEED in contents else LINE_FEED


def with_newline_style(*, contents: str, newline: str) -> str:
    """Normalize generated contents back to the authored newline convention."""

    normalized: str = contents.replace(CARRIAGE_RETURN_LINE_FEED, LINE_FEED)
    if newline == LINE_FEED:
        return normalized
    return normalized.replace(LINE_FEED, newline)
