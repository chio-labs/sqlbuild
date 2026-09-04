"""Plain-text normalization and deterministic chunking."""

from __future__ import annotations

import re

_ANSI_ESCAPE: re.Pattern[str] = re.compile(
    r"(?:\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~])"
)


def strip_ansi(text: str) -> str:
    """Remove terminal control sequences from only the exported copy."""

    return _ANSI_ESCAPE.sub("", text)


def chunk_text(*, text: str, max_bytes: int) -> tuple[str, ...]:
    """Split text deterministically without splitting Unicode code points."""

    chunks: list[str] = []
    current: list[str] = []
    current_bytes: int = 0
    for character in text:
        character_bytes: int = len(character.encode("utf-8", "surrogateescape"))
        if current and current_bytes + character_bytes > max_bytes:
            chunks.append("".join(current))
            current = []
            current_bytes = 0
        current.append(character)
        current_bytes += character_bytes
    if current or not chunks:
        chunks.append("".join(current))
    return tuple(chunks)
