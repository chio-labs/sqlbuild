from dataclasses import dataclass


@dataclass(frozen=True)
class DirectPlanE2ETestCase:
    description: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class DirectPlanJsonE2ETestCase:
    description: str
    expected_selected_count: int
    expected_model_count: int
    expected_function_count: int


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


@dataclass(frozen=True)
class VirtualPlanSelectionGuardE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class VirtualSourceFreshnessPlanE2ETestCase:
    description: str
    expected_unchanged_fragments: tuple[str, ...]
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()
