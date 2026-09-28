"""Normalize stored view definitions for comparison with compatibility view SQL."""

from __future__ import annotations

import re

_CREATE_PREFIX: re.Pattern[str] = re.compile(
    r"^\s*(?:create|alter)\b.*?\bview\s+\S+.*?\bas\s+", re.IGNORECASE | re.DOTALL
)
_QUOTES: re.Pattern[str] = re.compile(r"[\"`\[\]]")
_WHITESPACE: re.Pattern[str] = re.compile(r"\s+")
_PUNCTUATION_SPACE: re.Pattern[str] = re.compile(r"\s*([,()])\s*")


def view_definitions_match(*, definition: str, sql: str) -> bool:
    """Return whether two view bodies match, ignoring quoting, case, whitespace, and CREATE."""

    return _normalized(definition) == _normalized(sql)


def _normalized(text: str) -> str:
    body: str = _CREATE_PREFIX.sub("", text, count=1)
    body = _QUOTES.sub("", body).lower()
    body = _PUNCTUATION_SPACE.sub(r"\1", body)
    return _WHITESPACE.sub(" ", body).strip().rstrip(";").strip()
