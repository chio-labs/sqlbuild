"""Find similar unit pairs from normalised identity keys and shared fingerprints."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from itertools import combinations

from scripts.dupscore.constants import (
    CATEGORY_EXACT,
    CATEGORY_NEAR_MISS,
    CATEGORY_RENAMED,
    CLONE_CANDIDATE_MIN_JACCARD,
    CLONE_MAX_FINGERPRINT_UNITS,
    CLONE_MIN_FINGERPRINTS,
)
from scripts.dupscore.models import ClonePair, CloneUnit

_MIN_POSTING_UNITS: int = 2


def find_clone_pairs(
    *,
    units: list[CloneUnit],
    fingerprints: list[frozenset[int]],
    min_similarity: float,
) -> list[ClonePair]:
    """Return identical-stream pairs plus near-miss pairs above the similarity threshold."""

    pairs: dict[tuple[int, int], ClonePair] = {}
    for left, right in _identical_stream_pairs(units):
        category: str = (
            CATEGORY_EXACT
            if units[left].concrete_key == units[right].concrete_key
            else CATEGORY_RENAMED
        )
        pairs[(left, right)] = ClonePair(left=left, right=right, similarity=1.0, category=category)

    postings: dict[int, list[int]] = {}
    for unit_index, unit_fingerprints in enumerate(fingerprints):
        for fingerprint in unit_fingerprints:
            postings.setdefault(fingerprint, []).append(unit_index)
    boilerplate: set[int] = {
        fingerprint
        for fingerprint, members in postings.items()
        if len(members) > CLONE_MAX_FINGERPRINT_UNITS
    }
    distinctive_sizes: list[int] = [
        len(unit_fingerprints - boilerplate) for unit_fingerprints in fingerprints
    ]
    shared_counts: Counter[tuple[int, int]] = Counter()
    for fingerprint, members in postings.items():
        if fingerprint in boilerplate or len(members) < _MIN_POSTING_UNITS:
            continue
        shared_counts.update(combinations(members, 2))

    for (left, right), shared in shared_counts.items():
        if (left, right) in pairs or units[left].language != units[right].language:
            continue
        left_size: int = distinctive_sizes[left]
        right_size: int = distinctive_sizes[right]
        if min(left_size, right_size) < CLONE_MIN_FINGERPRINTS:
            continue
        if shared / (left_size + right_size - shared) < CLONE_CANDIDATE_MIN_JACCARD:
            continue
        similarity: float = _stream_similarity(
            left=units[left].normalized,
            right=units[right].normalized,
            min_similarity=min_similarity,
        )
        if similarity >= min_similarity:
            pairs[(left, right)] = ClonePair(
                left=left,
                right=right,
                similarity=round(similarity, 4),
                category=CATEGORY_NEAR_MISS,
            )
    return [pairs[key] for key in sorted(pairs)]


def _stream_similarity(
    *,
    left: tuple[str, ...],
    right: tuple[str, ...],
    min_similarity: float,
) -> float:
    shorter, longer = sorted((len(left), len(right)))
    if 2 * shorter / (shorter + longer) < min_similarity:
        return 0.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _identical_stream_pairs(units: list[CloneUnit]) -> list[tuple[int, int]]:
    groups: dict[tuple[str, str], list[int]] = {}
    for unit_index, unit in enumerate(units):
        groups.setdefault((unit.language, unit.normalized_key), []).append(unit_index)
    identical: list[tuple[int, int]] = []
    for members in groups.values():
        identical.extend(combinations(members, 2))
    return identical
