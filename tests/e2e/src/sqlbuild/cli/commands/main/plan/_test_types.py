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
class DirectChangesOnlyJsonE2ETestCase:
    description: str
    expected_reasons_by_name: dict[str, str]
    unexpected_json_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DirectChangesOnlyReplayE2ETestCase:
    description: str
    policy_fragment: str
    expected_backfill_action: str
    expected_backfill_duration: str | None


@dataclass(frozen=True)
class DirectChangesOnlySchemaReplayE2ETestCase:
    description: str
    expected_reason: str
    expected_backfill_action: str
    expected_backfill_duration: str | None


@dataclass(frozen=True)
class DirectChangesOnlyFunctionReplayE2ETestCase:
    description: str
    expected_reason: str
    expected_backfill_action: str
    expected_backfill_duration: str | None


@dataclass(frozen=True)
class DirectChangesOnlySelectorE2ETestCase:
    description: str
    selector: str
    expected_selected_count: int
    expected_model_names: tuple[str, ...]
    unexpected_model_names: tuple[str, ...]


@dataclass(frozen=True)
class DirectFunctionIdentityE2ETestCase:
    description: str
    expected_initial_count: int
    expected_changed_count: int
    expected_model_name: str


@dataclass(frozen=True)
class DirectFunctionSelectorE2ETestCase:
    description: str
    selector: str
    expected_plan_fragment: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]


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
