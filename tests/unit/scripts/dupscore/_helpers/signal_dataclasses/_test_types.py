from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataclassOverlapPairTestCase:
    description: str
    sources: dict[str, str]
    expected_top_pair: tuple[str, str]


@dataclass(frozen=True)
class DataclassOverlapSuppressionTestCase:
    description: str
    sources: dict[str, str]
    expected_entry_count: int
