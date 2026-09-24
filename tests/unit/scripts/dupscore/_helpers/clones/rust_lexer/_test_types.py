from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LexRustTestCase:
    description: str
    source: str
    expected_tokens: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class LexLineTestCase:
    description: str
    source: str
    token_text: str
    expected_line: int
