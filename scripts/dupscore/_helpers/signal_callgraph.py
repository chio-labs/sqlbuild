"""Signal: IDF-weighted shared-leaves / disjoint-middles call-graph shape."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations

from scripts.dupscore._helpers.source_provider import package_of, sorted_pair
from scripts.dupscore.constants import (
    MAX_LEAF_USERS_FOR_PAIRING,
    MIN_REACHABLE_FUNCTIONS,
    MIN_SHARED_LEAVES,
    SIGNAL_NAME_CALLGRAPH,
)
from scripts.dupscore.models import ProjectFacts, SignalPairScore, SignalRanking

_EVIDENCE_LEAF_SAMPLE: int = 6


@dataclass(frozen=True, slots=True)
class _FunctionProfile:
    leaves: frozenset[str]
    middles: frozenset[str]


def score_callgraph_shape(facts: ProjectFacts) -> SignalRanking:
    """Rank package pairs by parallel-derivation call-graph shape."""

    edges, node_modules = _build_call_graph(facts)
    reachable: dict[str, frozenset[str]] = _reachable_sets(edges)
    profiles: dict[str, _FunctionProfile] = _build_profiles(edges=edges, reachable=reachable)
    document_frequency: dict[str, int] = _document_frequency(profiles)
    profile_count: int = len(profiles)

    def inverse_frequency(item: str) -> float:
        return math.log1p(profile_count / (1 + document_frequency.get(item, 0)))

    best_per_pair: dict[tuple[str, str], SignalPairScore] = {}
    for left, right in _candidate_pairs(profiles=profiles, node_modules=node_modules):
        if right in reachable.get(left, frozenset()) or left in reachable.get(right, frozenset()):
            continue
        pair_score: SignalPairScore | None = _score_function_pair(
            left=left,
            right=right,
            profiles=profiles,
            node_modules=node_modules,
            inverse_frequency=inverse_frequency,
        )
        if pair_score is None:
            continue
        existing: SignalPairScore | None = best_per_pair.get(pair_score.package_pair)
        if existing is None or (-pair_score.score, pair_score.evidence) < (
            -existing.score,
            existing.evidence,
        ):
            best_per_pair[pair_score.package_pair] = pair_score

    ordered: list[SignalPairScore] = sorted(
        best_per_pair.values(),
        key=lambda entry: (-entry.score, entry.package_pair, entry.evidence),
    )
    return SignalRanking(signal_name=SIGNAL_NAME_CALLGRAPH, entries=tuple(ordered))


def _build_call_graph(facts: ProjectFacts) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    node_modules: dict[str, str] = {}
    raw_edges: dict[str, tuple[str, ...]] = {}
    for module_facts in facts.modules:
        for function in module_facts.functions:
            node_modules[function.qualified_name] = module_facts.module
            raw_edges[function.qualified_name] = function.resolved_calls
    edges: dict[str, tuple[str, ...]] = {}
    for node, calls in raw_edges.items():
        retained: list[str] = []
        for call in calls:
            if call in node_modules and call != node:
                retained.append(call)
        edges[node] = tuple(retained)
    return edges, node_modules


def _reachable_sets(edges: dict[str, tuple[str, ...]]) -> dict[str, frozenset[str]]:
    memo: dict[str, frozenset[str]] = {}
    for root in sorted(edges):
        if root in memo:
            continue
        stack: list[str] = [root]
        visiting: set[str] = set()
        pending: dict[str, list[str]] = {}
        accumulated: dict[str, set[str]] = {}
        while stack:
            node: str = stack[-1]
            if node in memo:
                _ = stack.pop()
                continue
            if node not in accumulated:
                accumulated[node] = set()
                visiting.add(node)
                pending[node] = sorted(edges.get(node, ()), reverse=True)
            if pending[node]:
                successor: str = pending[node].pop()
                accumulated[node].add(successor)
                if successor in memo:
                    accumulated[node] |= memo[successor]
                elif successor not in visiting:
                    stack.append(successor)
                continue
            _ = stack.pop()
            visiting.discard(node)
            memo[node] = frozenset(accumulated[node])
            if stack:
                parent: str = stack[-1]
                accumulated[parent] |= memo[node]
    return memo


def _build_profiles(
    *,
    edges: dict[str, tuple[str, ...]],
    reachable: dict[str, frozenset[str]],
) -> dict[str, _FunctionProfile]:
    leaves_all: set[str] = {node for node, calls in edges.items() if not calls}
    profiles: dict[str, _FunctionProfile] = {}
    for node, reached in reachable.items():
        if len(reached) < MIN_REACHABLE_FUNCTIONS:
            continue
        leaves: frozenset[str] = frozenset(item for item in reached if item in leaves_all)
        if len(leaves) < MIN_SHARED_LEAVES:
            continue
        middles: frozenset[str] = frozenset(item for item in reached if item not in leaves_all)
        profiles[node] = _FunctionProfile(leaves=leaves, middles=middles)
    return profiles


def _document_frequency(profiles: dict[str, _FunctionProfile]) -> dict[str, int]:
    frequency: dict[str, int] = {}
    for profile in profiles.values():
        for item in profile.leaves | profile.middles:
            frequency[item] = frequency.get(item, 0) + 1
    return frequency


def _candidate_pairs(
    *,
    profiles: dict[str, _FunctionProfile],
    node_modules: dict[str, str],
) -> list[tuple[str, str]]:
    users_by_leaf: dict[str, list[str]] = {}
    for node in sorted(profiles):
        for leaf in profiles[node].leaves:
            users_by_leaf.setdefault(leaf, []).append(node)
    pairs: set[tuple[str, str]] = set()
    for users in users_by_leaf.values():
        if len(users) > MAX_LEAF_USERS_FOR_PAIRING:
            continue
        for left, right in combinations(sorted(users), 2):
            if node_modules[left] != node_modules[right]:
                pairs.add((left, right))
    return sorted(pairs)


def _score_function_pair(
    *,
    left: str,
    right: str,
    profiles: dict[str, _FunctionProfile],
    node_modules: dict[str, str],
    inverse_frequency: Callable[[str], float],
) -> SignalPairScore | None:
    left_profile: _FunctionProfile = profiles[left]
    right_profile: _FunctionProfile = profiles[right]
    shared_leaves: frozenset[str] = left_profile.leaves & right_profile.leaves
    if len(shared_leaves) < MIN_SHARED_LEAVES:
        return None
    shared_weight: float = sum(inverse_frequency(item) for item in shared_leaves)
    union_weight: float = sum(
        inverse_frequency(item) for item in left_profile.leaves | right_profile.leaves
    )
    if union_weight <= 0:
        return None
    leaf_similarity: float = shared_weight / union_weight
    middle_union: frozenset[str] = left_profile.middles | right_profile.middles
    middle_shared_weight: float = sum(
        inverse_frequency(item) for item in left_profile.middles & right_profile.middles
    )
    middle_union_weight: float = sum(inverse_frequency(item) for item in middle_union)
    middle_similarity: float = (
        middle_shared_weight / middle_union_weight if middle_union_weight > 0 else 1.0
    )
    score: float = leaf_similarity * (1.0 - middle_similarity) * math.sqrt(max(shared_weight, 0.0))
    if score <= 0:
        return None
    rare_shared: list[str] = sorted(
        shared_leaves, key=lambda item: (-inverse_frequency(item), item)
    )
    evidence: tuple[str, ...] = (
        f"entrypoints {left} <-> {right}",
        "shared rare leaves: " + ", ".join(rare_shared[:_EVIDENCE_LEAF_SAMPLE]),
    )
    package_pair: tuple[str, str] = sorted_pair(
        left=package_of(node_modules[left]),
        right=package_of(node_modules[right]),
    )
    return SignalPairScore(package_pair=package_pair, score=score, evidence=evidence)
