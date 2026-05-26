from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualPlanE2ETestCase:
    description: str
    seed_matching_refs: bool
    command: tuple[str, ...]
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class VirtualPlanJsonE2ETestCase:
    description: str
    expected_json_fragments: tuple[str, ...]
