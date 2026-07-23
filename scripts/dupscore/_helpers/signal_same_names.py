"""Signal: identical public function names across modules, ranked by body similarity."""

from __future__ import annotations

from itertools import combinations

from scripts.dupscore._helpers.source_provider import package_of, sorted_pair
from scripts.dupscore.constants import (
    GENERIC_FUNCTION_NAMES,
    HELPERS_ROLE_SEGMENT,
    MAIN_ROLE_SEGMENT,
    MAX_NAME_WEIGHT_WORDS,
    SIGNAL_NAME_SAME_NAME,
)
from scripts.dupscore.models import FunctionFact, ProjectFacts, SignalPairScore, SignalRanking

_MIN_DEFINITIONS_FOR_TWIN: int = 2


def score_same_name_symbols(facts: ProjectFacts) -> SignalRanking:
    """Rank package pairs defining identically named, similarly bodied public functions."""

    functions_by_name: dict[str, list[FunctionFact]] = {}
    for module_facts in facts.modules:
        for function in module_facts.functions:
            if function.public and function.name not in GENERIC_FUNCTION_NAMES:
                functions_by_name.setdefault(function.name, []).append(function)

    best_per_pair: dict[tuple[str, str], SignalPairScore] = {}
    for name in sorted(functions_by_name):
        definitions: list[FunctionFact] = functions_by_name[name]
        if len(definitions) < _MIN_DEFINITIONS_FOR_TWIN:
            continue
        for left, right in combinations(definitions, 2):
            if left.module == right.module:
                continue
            if _is_wrapper_twin(left=left, right=right):
                continue
            union_tokens: frozenset[str] = left.body_tokens | right.body_tokens
            if not union_tokens:
                continue
            similarity: float = len(left.body_tokens & right.body_tokens) / len(union_tokens)
            name_weight: float = (
                min(len(name.split("_")), MAX_NAME_WEIGHT_WORDS) / MAX_NAME_WEIGHT_WORDS
            )
            score: float = similarity * name_weight
            if score <= 0:
                continue
            evidence: tuple[str, ...] = (
                f"twin {name}: {left.module}:{left.lineno} <-> {right.module}:{right.lineno}",
                f"body token similarity {similarity:.2f}",
            )
            package_pair: tuple[str, str] = sorted_pair(
                left=package_of(left.module),
                right=package_of(right.module),
            )
            candidate: SignalPairScore = SignalPairScore(
                package_pair=package_pair, score=score, evidence=evidence
            )
            existing: SignalPairScore | None = best_per_pair.get(package_pair)
            if existing is None or (-candidate.score, candidate.evidence) < (
                -existing.score,
                existing.evidence,
            ):
                best_per_pair[package_pair] = candidate

    ordered: list[SignalPairScore] = sorted(
        best_per_pair.values(),
        key=lambda entry: (-entry.score, entry.package_pair, entry.evidence),
    )
    return SignalRanking(signal_name=SIGNAL_NAME_SAME_NAME, entries=tuple(ordered))


def _is_wrapper_twin(*, left: FunctionFact, right: FunctionFact) -> bool:
    if package_of(left.module) != package_of(right.module):
        return False
    left_segments: frozenset[str] = frozenset(left.module.split("."))
    right_segments: frozenset[str] = frozenset(right.module.split("."))
    left_is_main: bool = MAIN_ROLE_SEGMENT in left_segments
    right_is_main: bool = MAIN_ROLE_SEGMENT in right_segments
    left_is_helper: bool = HELPERS_ROLE_SEGMENT in left_segments
    right_is_helper: bool = HELPERS_ROLE_SEGMENT in right_segments
    return (left_is_main and right_is_helper) or (left_is_helper and right_is_main)
