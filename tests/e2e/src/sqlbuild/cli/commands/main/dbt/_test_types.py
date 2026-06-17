from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DbtExecutionQueryAssertion:
    description: str
    sql: str
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPlanCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_selected_models: tuple[str, ...]
    expected_dbt_skipped: bool
    expected_sqlbuild_skipped: bool
    expected_anchor_terms: tuple[str, ...] = ()
    expected_path_translations: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DbtPlanRelativeProjectDirTestCase:
    description: str
    command: tuple[str, ...]
    expected_selected_models: tuple[str, ...]


@dataclass(frozen=True)
class DbtPlanHumanCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtPlanErrorCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stderr_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtExecutionCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_row_counts: tuple[tuple[str, int], ...]
    unexpected_relations: tuple[str, ...] = ()
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_absent_stdout_fragments: tuple[str, ...] = ()
    expected_query_assertions: tuple[DbtExecutionQueryAssertion, ...] = ()
    expected_planned_sqlbuild_models: tuple[str, ...] | None = None
    rerun_count: int = 1


@dataclass(frozen=True)
class DbtExecutionFailureCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_stdout_fragments: tuple[str, ...]
    expected_absent_relations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DbtMissingRelationGuardE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_returncode: int
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_relations: tuple[str, ...]


@dataclass(frozen=True)
class DbtExistingRelationGuardE2ETestCase:
    description: str
    command: tuple[str, ...]
    setup_sql: str
    expected_returncode: int
    expected_stdout_fragments: tuple[str, ...]
    unexpected_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtReuseFromE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_destination_rows: tuple[tuple[object, ...], ...]
    expected_downstream_rows: tuple[tuple[object, ...], ...]
    expected_rerun_destination_rows: tuple[tuple[object, ...], ...]
    expected_fingerprint_rows: tuple[tuple[object, ...], ...]
    expected_metadata_json: str
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_relations: tuple[tuple[str, str], ...]
    expected_absent_stdout_fragments: tuple[str, ...]
    expected_rerun_absent_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtSeededReuseFromE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_destination_rows: tuple[tuple[object, ...], ...]
    expected_downstream_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_rerun_absent_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtDependencyBaselineReuseFromE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_destination_rows: tuple[tuple[object, ...], ...]
    expected_downstream_rows: tuple[tuple[object, ...], ...]
    expected_dbt_fingerprint_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtDependencyBaselinePlanJsonE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_selected_models: tuple[str, ...]
    expected_seeded_reuse_unique_ids: tuple[str, ...]
    expected_entry_action: str
    expected_entry_reason: str
    expected_entry_materialization: str


@dataclass(frozen=True)
class DbtLineageE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_node_ids: tuple[str, ...]
    expected_edges: tuple[tuple[str, str], ...]
    expected_focus: tuple[str, ...]
    expected_direction: str
    expected_node_metadata: tuple[tuple[str, str, object], ...] = ()


@dataclass(frozen=True)
class DbtLineageTextE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_stderr_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtLineageErrorE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_stderr_fragments: tuple[str, ...]
    setup: Callable[[Path], None] | None = None


@dataclass(frozen=True)
class DbtMultiNodeCompleteReuseFromE2ETestCase:
    description: str
    command: tuple[str, ...]
    failure_sql: str
    recovery_sql: str
    expected_failed_destination_rows: tuple[tuple[str, int], ...]
    expected_failed_fingerprint_rows: tuple[tuple[str], ...]
    expected_rerun_downstream_rows: tuple[tuple[str, int], ...]
    expected_rerun_fingerprint_rows: tuple[tuple[str], ...]
    expected_absent_failed_relation: tuple[str, str]
    expected_failed_absent_stdout_fragments: tuple[str, ...]
    expected_rerun_stdout_fragments: tuple[str, ...]
    expected_rerun_absent_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtMultiNodeSeededReuseFromE2ETestCase:
    description: str
    command: tuple[str, ...]
    failure_sql: str
    recovery_sql: str
    expected_failed_destination_rows: tuple[tuple[str, int, int], ...]
    expected_absent_failed_relation: tuple[str, str]
    expected_failed_absent_stdout_fragments: tuple[str, ...]
    expected_rerun_stdout_fragments: tuple[str, ...]
    expected_rerun_absent_stdout_fragments: tuple[str, ...]
    expected_rerun_downstream_rows: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class DbtSnapshotSeededReuseFromE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_destination_rows: tuple[tuple[int, int], ...]
    expected_downstream_rows: tuple[tuple[int, int], ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_rerun_absent_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtTestCliTestCase:
    description: str
    command: tuple[str, ...]
    setup_command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_stdout_fragments: tuple[str, ...] = ()
    expected_query_assertions: tuple[DbtExecutionQueryAssertion, ...] = ()


@dataclass(frozen=True)
class DbtScenarioCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_relations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DbtDebugCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_returncode: int = 0


@dataclass(frozen=True)
class DbtInitDuckDbE2ETestCase:
    description: str
    expected_generated_files: tuple[str, ...]
    unexpected_generated_paths: tuple[str, ...]
    expected_toml_fragments: tuple[str, ...]
    unexpected_toml_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_dbt_stdout_fragments: tuple[str, ...]
    expected_dbt_fingerprint_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPhase11ExecutionTestCase:
    description: str
    expected_current_stdout_fragments: tuple[str, ...]
    expected_current_absent_stdout_fragments: tuple[str, ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]
    expected_fingerprint_unique_ids: tuple[str, ...]


@dataclass(frozen=True)
class DbtPhase11SourceBlockingTestCase:
    description: str
    expected_returncode: int
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_relations: tuple[str, ...]
    expected_customer_rows: tuple[tuple[object, ...], ...]
    expected_source_freshness_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPhase11SourceFreshnessChangeTestCase:
    description: str
    expected_current_stdout_fragments: tuple[str, ...]
    expected_plan_run_unique_ids: tuple[str, ...]
    expected_plan_reasons: tuple[str, ...]
    expected_plan_stale_sqlbuild_model_names: tuple[str, ...]
    expected_plan_current_unique_ids: tuple[str, ...]
    expected_source_freshness_rows: tuple[tuple[object, ...], ...]
    expected_changed_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPhase11DbtOnlySourceFreshnessTestCase:
    description: str
    expected_current_stdout_fragments: tuple[str, ...]
    expected_plan_run_unique_ids: tuple[str, ...]
    expected_plan_reasons: tuple[str, ...]
    expected_plan_stale_sqlbuild_model_names: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPhase11SourceObservationErrorTestCase:
    description: str
    expected_returncode: int
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_relations: tuple[str, ...]
    expected_source_freshness_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPhase11MultiSourceFreshnessTestCase:
    description: str
    expected_run_unique_ids: tuple[str, ...]
    expected_run_reasons: tuple[str, ...]
    expected_stale_sqlbuild_model_names: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPhase11QueryFilterFreshnessTestCase:
    description: str
    expected_run_unique_ids: tuple[str, ...]
    expected_run_reasons: tuple[str, ...]
    expected_stale_sqlbuild_model_names: tuple[str, ...]
    expected_source_freshness_rows: tuple[tuple[object, ...], ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPhase11FreshnessEdgeCaseTestCase:
    description: str
    expected_run_unique_ids: tuple[str, ...] = ()
    expected_run_reasons: tuple[str, ...] = ()
    expected_stale_sqlbuild_model_names: tuple[str, ...] = ()
    expected_rows: tuple[tuple[object, ...], ...] = ()
    expected_returncode: int = 0
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_source_freshness_rows: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class DbtPhase11ModelFailureTestCase:
    description: str
    expected_returncode: int
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_relations: tuple[str, ...]
    expected_customer_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPhase11NonModelWorkTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    unexpected_stdout_fragments: tuple[str, ...] = ()
    expected_returncode: int = 0


@dataclass(frozen=True)
class DbtPhase11SqlbuildNativePlanTestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtPhase11PlanOutputTestCase:
    description: str
    expected_current_unique_ids: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtPhase11ReplayFullTestCase:
    description: str
    expected_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
