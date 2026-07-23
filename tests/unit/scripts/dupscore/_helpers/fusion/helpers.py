from __future__ import annotations

from scripts.dupscore.models import SignalPairScore, SignalRanking


def ranking_of(*, signal_name: str, pairs: tuple[tuple[str, str], ...]) -> SignalRanking:
    entries: tuple[SignalPairScore, ...] = tuple(
        SignalPairScore(
            package_pair=pair, score=float(len(pairs) - index), evidence=(f"evidence {index}",)
        )
        for index, pair in enumerate(pairs)
    )
    return SignalRanking(signal_name=signal_name, entries=entries)
