"""Plain-text normalization and deterministic chunking."""

from __future__ import annotations

import re

from sqlbuild.runtime.output_capture.constants import (
    UTF8_CONTINUATION_BYTE_MASK,
    UTF8_CONTINUATION_BYTE_TAG,
)

_ANSI_ESCAPE: re.Pattern[str] = re.compile(
    r"(?:\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~])"
)


def strip_ansi(text: str) -> str:
    """Remove terminal control sequences from only the exported copy."""

    return _ANSI_ESCAPE.sub("", text)


def chunk_text(*, text: str, max_bytes: int) -> tuple[str, ...]:
    """Split text deterministically without splitting Unicode code points."""

    if text.isascii() and max_bytes > 0:
        if len(text) <= max_bytes:
            return (text,)
        return tuple(text[index : index + max_bytes] for index in range(0, len(text), max_bytes))
    try:
        encoded: bytes = text.encode("utf-8")
    except UnicodeEncodeError:
        return _chunk_text_by_character(text=text, max_bytes=max_bytes)
    if len(encoded) <= max_bytes:
        return (text,)
    return _chunk_utf8(encoded=encoded, max_bytes=max_bytes)


def _chunk_utf8(*, encoded: bytes, max_bytes: int) -> tuple[str, ...]:
    """Split valid UTF-8 greedily at the last code point boundary within each limit."""

    chunks: list[str] = []
    total: int = len(encoded)
    start: int = 0
    while start < total:
        end: int = start + max_bytes
        if end >= total:
            end = total
        else:
            while (
                end > start
                and encoded[end] & UTF8_CONTINUATION_BYTE_MASK == UTF8_CONTINUATION_BYTE_TAG
            ):
                end -= 1
            if end <= start:
                end = start + 1
                while (
                    end < total
                    and encoded[end] & UTF8_CONTINUATION_BYTE_MASK == UTF8_CONTINUATION_BYTE_TAG
                ):
                    end += 1
        chunks.append(encoded[start:end].decode("utf-8"))
        start = end
    if not chunks:
        chunks.append("")
    return tuple(chunks)


def _chunk_text_by_character(*, text: str, max_bytes: int) -> tuple[str, ...]:
    """Split text containing lone surrogates, which surrogateescape maps to single bytes."""

    if len(text) <= max_bytes and len(text.encode("utf-8", "surrogateescape")) <= max_bytes:
        return (text,)

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
