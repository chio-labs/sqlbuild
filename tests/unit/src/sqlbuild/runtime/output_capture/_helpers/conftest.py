"""Shared fixtures for output capture text chunking tests."""

import pytest

from tests.unit.src.sqlbuild.runtime.output_capture._helpers._test_types import ChunkTextFunction


def _reference_chunk_text(*, text: str, max_bytes: int) -> tuple[str, ...]:
    """Copy of the original character-at-a-time chunker that defines the stored contract."""

    if text.isascii() and max_bytes > 0:
        if len(text) <= max_bytes:
            return (text,)
        return tuple(text[index : index + max_bytes] for index in range(0, len(text), max_bytes))
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


@pytest.fixture
def reference_chunk_text() -> ChunkTextFunction:
    """Return the reference oracle for chunk boundaries and text."""

    return _reference_chunk_text
