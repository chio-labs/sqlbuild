from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NearMissFloorTestCase:
    description: str
    shared_tokens: int
    differing_tokens: int
    min_similarity: float
    expected_categories: list[str]
