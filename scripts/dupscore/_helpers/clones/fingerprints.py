"""Winnowed k-gram fingerprints over normalised token streams (MOSS style)."""

from __future__ import annotations

import zlib
from functools import cache

from scripts.dupscore.constants import CLONE_KGRAM_SIZE, CLONE_WINNOW_WINDOW


def fingerprint_tokens(normalized: tuple[str, ...]) -> frozenset[int]:
    """Select the minimum k-gram hash of every window of consecutive k-grams."""

    identifiers: list[int] = [_token_identifier(text) for text in normalized]
    gram_count: int = len(identifiers) - CLONE_KGRAM_SIZE + 1
    if gram_count <= 0:
        return frozenset()
    hashes: list[int] = [
        hash(tuple(identifiers[offset : offset + CLONE_KGRAM_SIZE])) for offset in range(gram_count)
    ]
    if gram_count <= CLONE_WINNOW_WINDOW:
        return frozenset({min(hashes)})
    return frozenset(
        min(hashes[offset : offset + CLONE_WINNOW_WINDOW])
        for offset in range(gram_count - CLONE_WINNOW_WINDOW + 1)
    )


@cache
def _token_identifier(text: str) -> int:
    return zlib.crc32(text.encode("utf-8"))
