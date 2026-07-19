from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateFaninPairTestCase:
    description: str
    sources: dict[str, str]
    persisted_state_surfaces: tuple[str, ...]
    expected_top_pair: tuple[str, str]
    expected_top_score: float


@dataclass(frozen=True)
class StateFaninSuppressionTestCase:
    description: str
    sources: dict[str, str]
    persisted_state_surfaces: tuple[str, ...]
    expected_entry_count: int
