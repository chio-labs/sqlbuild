"""Recognize Snowflake statements that may switch the session database."""

from __future__ import annotations

import re

_LEADING_WHITESPACE: re.Pattern[str] = re.compile(r"\s*+")
_FIRST_WORD: re.Pattern[str] = re.compile(r"[A-Za-z]++")
_LINE_COMMENT_START: str = "--"
_BLOCK_COMMENT_START: str = "/*"
_BLOCK_COMMENT_END: str = "*/"
_NEWLINE: str = "\n"
_SESSION_SWITCHING_WORDS: frozenset[str] = frozenset({"USE", "CALL", "EXECUTE", "BEGIN", "DECLARE"})


def may_switch_session_database(sql: str) -> bool:
    """Return whether ``sql`` may change the current database; unreadable text counts as yes."""

    position: int | None = _first_code_position(sql=sql)
    if position is None:
        return True
    word: re.Match[str] | None = _FIRST_WORD.match(sql, position)
    return word is not None and word.group(0).upper() in _SESSION_SWITCHING_WORDS


def _first_code_position(*, sql: str) -> int | None:
    position: int = 0
    while True:
        whitespace: re.Match[str] | None = _LEADING_WHITESPACE.match(sql, position)
        position = position if whitespace is None else whitespace.end()
        if sql.startswith(_LINE_COMMENT_START, position):
            line_end: int = sql.find(_NEWLINE, position)
            if line_end < 0:
                return len(sql)
            position = line_end + 1
            continue
        if not sql.startswith(_BLOCK_COMMENT_START, position):
            return position
        comment_end: int = sql.find(_BLOCK_COMMENT_END, position + len(_BLOCK_COMMENT_START))
        if comment_end < 0:
            return None
        position = comment_end + len(_BLOCK_COMMENT_END)
