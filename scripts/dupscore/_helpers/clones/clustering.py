"""Group clone pairs into transitive clusters and rank them."""

from __future__ import annotations

from collections.abc import Callable

from scripts.dupscore.constants import CATEGORY_ORDER
from scripts.dupscore.models import (
    CloneCluster,
    CloneMember,
    ClonePair,
    ClonePairLink,
    CloneUnit,
)


def cluster_clone_pairs(
    *,
    units: list[CloneUnit],
    pairs: list[ClonePair],
    change_of: Callable[[CloneUnit], str | None],
) -> list[CloneCluster]:
    """Group pairs into connected components ordered by estimated duplicated tokens."""

    clusters: list[CloneCluster] = [
        _build_cluster(units=units, pairs=component, change_of=change_of)
        for component in _connected_pair_groups(pairs)
    ]
    return sorted(clusters, key=_cluster_sort_key)


def _connected_pair_groups(pairs: list[ClonePair]) -> list[list[ClonePair]]:
    neighbours: dict[int, list[int]] = {}
    for pair in pairs:
        neighbours.setdefault(pair.left, []).append(pair.right)
        neighbours.setdefault(pair.right, []).append(pair.left)
    component_of: dict[int, int] = {}
    for root in sorted(neighbours):
        if root in component_of:
            continue
        pending: list[int] = [root]
        while pending:
            node: int = pending.pop()
            if node in component_of:
                continue
            component_of[node] = root
            pending.extend(neighbours[node])
    grouped: dict[int, list[ClonePair]] = {}
    for pair in pairs:
        grouped.setdefault(component_of[pair.left], []).append(pair)
    return list(grouped.values())


def _unit_indexes(pairs: list[ClonePair]) -> set[int]:
    indexes: set[int] = set()
    for pair in pairs:
        indexes.update((pair.left, pair.right))
    return indexes


def _build_cluster(
    *,
    units: list[CloneUnit],
    pairs: list[ClonePair],
    change_of: Callable[[CloneUnit], str | None],
) -> CloneCluster:
    unit_indexes: list[int] = sorted(
        _unit_indexes(pairs),
        key=lambda index: (units[index].path, units[index].start_line, units[index].name),
    )
    position: dict[int, int] = {unit_index: slot for slot, unit_index in enumerate(unit_indexes)}
    best_similarity: dict[int, float] = {}
    for pair in pairs:
        for unit_index in (pair.left, pair.right):
            best_similarity[unit_index] = max(best_similarity.get(unit_index, 0.0), pair.similarity)
    weights: list[float] = [
        len(units[unit_index].normalized) * best_similarity[unit_index]
        for unit_index in unit_indexes
    ]
    links: list[ClonePairLink] = sorted(
        (
            ClonePairLink(
                left=min(position[pair.left], position[pair.right]),
                right=max(position[pair.left], position[pair.right]),
                similarity=pair.similarity,
                category=pair.category,
            )
            for pair in pairs
        ),
        key=lambda link: (link.left, link.right),
    )
    similarities: list[float] = [pair.similarity for pair in pairs]
    category: str = max(
        (pair.category for pair in pairs), key=lambda value: CATEGORY_ORDER.index(value)
    )
    members: tuple[CloneMember, ...] = tuple(
        CloneMember(
            language=units[unit_index].language,
            path=units[unit_index].path,
            name=units[unit_index].name,
            start_line=units[unit_index].start_line,
            end_line=units[unit_index].end_line,
            tokens=len(units[unit_index].normalized),
            change=change_of(units[unit_index]),
        )
        for unit_index in unit_indexes
    )
    return CloneCluster(
        category=category,
        similarity_min=min(similarities),
        similarity_max=max(similarities),
        duplicated_tokens=round(sum(weights) - max(weights)),
        members=members,
        links=tuple(links),
    )


def _cluster_sort_key(cluster: CloneCluster) -> tuple[int, float, str, int]:
    first: CloneMember = cluster.members[0]
    return (-cluster.duplicated_tokens, -cluster.similarity_max, first.path, first.start_line)
