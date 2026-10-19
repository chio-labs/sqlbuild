"""SQL statement classification for the SQLite write gate."""

from __future__ import annotations


def leading_keyword(sql: str) -> str:
    """Return a statement's first keyword, skipping leading comments."""

    text: str = sql.lstrip()
    while text.startswith(("--", "/*")):
        text = (
            text.partition("\n")[2].lstrip()
            if text.startswith("--")
            else text.partition("*/")[2].lstrip()
        )
    word: str = text.split(None, 1)[0] if text else ""
    return word.rstrip(";(").upper()
