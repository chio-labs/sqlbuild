from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClusterPairsTestCase:
    description: str
    pairs: tuple[tuple[int, int, float, str], ...]
    expected_clusters: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class ClusterEstimateTestCase:
    description: str
    pairs: tuple[tuple[int, int, float, str], ...]
    expected_links: tuple[tuple[int, int], ...]
    expected_similarity_range: tuple[float, float]
    expected_duplicated_tokens: int
