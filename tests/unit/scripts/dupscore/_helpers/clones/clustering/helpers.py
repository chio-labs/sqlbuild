from __future__ import annotations

from scripts.dupscore._helpers.clones.tokens import build_clone_unit
from scripts.dupscore.models import CloneCluster, ClonePair, CloneUnit

_UNIT_SIZES: tuple[int, ...] = (100, 100, 90, 40, 40)


def build_units() -> list[CloneUnit]:
    return [
        build_clone_unit(
            language="python",
            path=f"src/sqlbuild/module_{position}.py",
            name=f"function_{position}",
            start_line=1,
            end_line=10,
            normalized=["$id"] * size,
            concrete=["name"] * size,
        )
        for position, size in enumerate(_UNIT_SIZES)
    ]


def build_pairs(specs: tuple[tuple[int, int, float, str], ...]) -> list[ClonePair]:
    return [
        ClonePair(left=left, right=right, similarity=similarity, category=category)
        for left, right, similarity, category in specs
    ]


def no_change(unit: CloneUnit) -> str | None:
    return None


def summarize_clusters(clusters: list[CloneCluster]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    summaries: list[tuple[str, tuple[str, ...]]] = []
    for cluster in clusters:
        names: tuple[str, ...] = tuple(member.name for member in cluster.members)
        summaries.append((cluster.category, names))
    return tuple(summaries)
