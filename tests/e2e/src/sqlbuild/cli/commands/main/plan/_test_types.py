from dataclasses import dataclass


@dataclass(frozen=True)
class DirectModeVirtualFlagGuardE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_error_fragment: str
    expected_exit_code: int = 1


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
class VirtualChangesOnlyCurrentSeedParityE2ETestCase:
    description: str
    expected_plan_selected_fragment: str
    expected_kept_model: str
    expected_pruned_seed: str


@dataclass(frozen=True)
class VirtualPlanBuildParityE2ETestCase:
    description: str
    expected_plan_exit_code: int
    expected_build_exit_code: int
    expected_fragments: tuple[str, ...]
    unexpected_plan_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class VirtualSourceFreshnessPlanE2ETestCase:
    description: str
    expected_unchanged_fragments: tuple[str, ...]
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...] = ()
    project_suffix: str | None = None
    data_version_sql: str | None = None
    include_freshness: bool = True
    source_freshness_type: str = "timestamp"
    warehouse_column_type: str = "TIMESTAMP"
