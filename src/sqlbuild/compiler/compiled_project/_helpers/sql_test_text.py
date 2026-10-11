"""Python `re` matches the native SQL-test attachment checks read, isolated pending regex."""

from __future__ import annotations

import re

_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z_][\w$]*")


def identifier_tokens(sql: str) -> list[str]:
    """Every identifier token, casefolded, first occurrence first."""

    return list(dict.fromkeys(match.casefold() for match in _IDENTIFIER_PATTERN.findall(sql)))


def reads_word(*, sql: str, word: str) -> bool:
    """Whether ``sql`` contains ``word``, ignoring case, outside a longer word."""

    return re.search(rf"(?<![\w$]){re.escape(word)}(?![\w$])", sql, re.IGNORECASE) is not None
