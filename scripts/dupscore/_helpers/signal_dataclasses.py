"""Signal: public dataclass field-name overlap across modules."""

from __future__ import annotations

from itertools import combinations

from scripts.dupscore._helpers.source_provider import package_of, sorted_pair
from scripts.dupscore.constants import MIN_SHARED_DATACLASS_FIELDS, SIGNAL_NAME_DATACLASS_OVERLAP
from scripts.dupscore.models import ProjectFacts, SignalPairScore, SignalRanking


def score_dataclass_overlap(facts: ProjectFacts) -> SignalRanking:
    """Rank package pairs whose public models share large field-name sets."""

    models: list[tuple[str, str, frozenset[str]]] = []
    for module_facts in facts.modules:
        for class_fact in module_facts.classes:
            eligible: bool = (
                class_fact.dataclass_like
                and class_fact.public
                and len(class_fact.field_names) >= MIN_SHARED_DATACLASS_FIELDS
            )
            if eligible:
                models.append(
                    (
                        class_fact.qualified_name,
                        module_facts.module,
                        frozenset(class_fact.field_names),
                    )
                )

    best_per_pair: dict[tuple[str, str], SignalPairScore] = {}
    for (left_qual, left_module, left_fields), (
        right_qual,
        right_module,
        right_fields,
    ) in combinations(models, 2):
        if left_module == right_module:
            continue
        shared: frozenset[str] = left_fields & right_fields
        if len(shared) < MIN_SHARED_DATACLASS_FIELDS:
            continue
        jaccard: float = len(shared) / len(left_fields | right_fields)
        score: float = jaccard * len(shared)
        evidence: tuple[str, ...] = (
            f"models {left_qual} <-> {right_qual}",
            f"{len(shared)} shared fields: " + ", ".join(sorted(shared)),
        )
        package_pair: tuple[str, str] = sorted_pair(
            left=package_of(left_module),
            right=package_of(right_module),
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
    return SignalRanking(signal_name=SIGNAL_NAME_DATACLASS_OVERLAP, entries=tuple(ordered))
