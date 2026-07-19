"""Signal: distinct calling packages per configured persisted-state read method."""

from __future__ import annotations

from itertools import combinations

from scripts.dupscore._helpers.source_provider import package_of
from scripts.dupscore.constants import (
    MIN_STATE_FANIN_PACKAGES,
    SIGNAL_NAME_STATE_FANIN,
    STATE_READ_PREFIXES,
)
from scripts.dupscore.models import (
    DupscoreConfig,
    FunctionFact,
    ProjectFacts,
    SignalPairScore,
    SignalRanking,
)


def score_state_fanin(*, facts: ProjectFacts, config: DupscoreConfig) -> SignalRanking:
    """Rank package pairs that independently read the same persisted-state surface."""

    if not config.persisted_state_surfaces:
        return SignalRanking(signal_name=SIGNAL_NAME_STATE_FANIN, entries=())
    read_owners: dict[str, str] = _collect_state_read_methods(facts=facts, config=config)
    calling_packages: dict[str, set[str]] = {name: set() for name in read_owners}
    for module_facts in facts.modules:
        caller_package: str = package_of(module_facts.module)
        all_functions: list[FunctionFact] = list(module_facts.functions)
        for class_fact in module_facts.classes:
            all_functions.extend(class_fact.methods)
        for function in all_functions:
            for bare_name in function.bare_attribute_calls:
                if bare_name in calling_packages:
                    calling_packages[bare_name].add(caller_package)
            for call in function.resolved_calls:
                called_name: str = call.split("::")[-1]
                if called_name in calling_packages:
                    calling_packages[called_name].add(caller_package)

    pair_scores: dict[tuple[str, str], list[str]] = {}
    for method_name in sorted(read_owners):
        owner: str = read_owners[method_name]
        external: list[str] = sorted(
            caller for caller in calling_packages[method_name] if not owner.startswith(caller)
        )
        if len(external) < MIN_STATE_FANIN_PACKAGES:
            continue
        for left, right in combinations(external, 2):
            pair_scores.setdefault((left, right), []).append(method_name)

    entries: list[SignalPairScore] = []
    for pair in sorted(pair_scores):
        methods: list[str] = pair_scores[pair]
        evidence: tuple[str, ...] = ("co-read state methods: " + ", ".join(methods),)
        entries.append(
            SignalPairScore(package_pair=pair, score=float(len(methods)), evidence=evidence)
        )
    entries.sort(key=lambda entry: (-entry.score, entry.package_pair))
    return SignalRanking(signal_name=SIGNAL_NAME_STATE_FANIN, entries=tuple(entries))


def _collect_state_read_methods(*, facts: ProjectFacts, config: DupscoreConfig) -> dict[str, str]:
    owners: dict[str, str] = {}
    for module_facts in facts.modules:
        if not _is_state_surface(module=module_facts.module, config=config):
            continue
        for class_fact in module_facts.classes:
            for method in class_fact.methods:
                if method.name.startswith(STATE_READ_PREFIXES):
                    owners.setdefault(method.name, class_fact.qualified_name)
        for function in module_facts.functions:
            if function.public and function.name.startswith(STATE_READ_PREFIXES):
                owners.setdefault(function.name, module_facts.module)
    return owners


def _is_state_surface(*, module: str, config: DupscoreConfig) -> bool:
    for surface in config.persisted_state_surfaces:
        if module == surface or module.startswith(surface + "."):
            return True
    return False
