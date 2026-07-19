from __future__ import annotations

from dataclasses import dataclass

from scripts.dupscore.models import DupscoreConfig, SignalRanking


@dataclass(frozen=True)
class FuseRankingsTestCase:
    description: str
    rankings: tuple[SignalRanking, ...]
    config: DupscoreConfig
    expected_order: tuple[tuple[str, str], ...]
    expected_allowlisted_flags: tuple[bool, ...]


@dataclass(frozen=True)
class DomainFilterTestCase:
    description: str
    rankings: tuple[SignalRanking, ...]
    domain: str | None
    expected_pair_count: int
