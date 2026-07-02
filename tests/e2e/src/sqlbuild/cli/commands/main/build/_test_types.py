"""Test types for build e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BuildE2ETestCase:
    """Test case for sqb build e2e verification."""

    description: str
    expected_exit_code: int
    expected_table_names: tuple[str, ...]
    expected_view_names: tuple[str, ...]
    expected_seed_names: tuple[str, ...]
    expected_fact_orders_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_fact_orders_python_udf_data: tuple[tuple[object, ...], ...] = field(
        default_factory=tuple
    )
    expected_customer_orders_table_function_data: tuple[tuple[object, ...], ...] = field(
        default_factory=tuple
    )
    expected_dim_customers_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_waffle_types_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_daily_revenue_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_daily_order_partitioned_data: tuple[tuple[object, ...], ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class BuildNoTestsNoAuditsFlagE2ETestCase:
    """Test case for build test/audit opt-out flags."""

    description: str
    project_name: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    unexpected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_exit_code: int = 0


@dataclass(frozen=True)
class DependencyBaselineBuildE2ETestCase:
    """Test case for direct-mode dependency baseline reuse_from behavior."""

    description: str
    project_name: str
    upstream_sql: str
    downstream_sql: str
    prod_setup_sql: str
    setup_commands: tuple[tuple[str, ...], ...]
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    unexpected_stdout_fragments: tuple[str, ...]
    expected_upstream_rows: tuple[tuple[object, ...], ...]
    expected_downstream_rows: tuple[tuple[object, ...], ...]
    expected_fingerprint_rows: tuple[tuple[object, ...], ...]
    dev_setup_sql: str | None = None


@dataclass(frozen=True)
class DeferCloneBuildE2ETestCase:
    """Test case for direct-mode build defer clone behavior."""

    description: str
    project_name: str
    initial_upstream_sql: str
    changed_upstream_sql: str
    downstream_sql: str
    prod_build_command: tuple[str, ...]
    dev_build_command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    unexpected_stdout_fragments: tuple[str, ...]
    expected_prod_upstream_rows: tuple[tuple[object, ...], ...]
    expected_dev_upstream_rows: tuple[tuple[object, ...], ...]
    expected_dev_downstream_rows: tuple[tuple[object, ...], ...]
    expected_fingerprint_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SelectionAwareStalenessBuildE2ETestCase:
    description: str
    project_name: str
    initial_command: tuple[str, ...]
    mixed_command: tuple[str, ...]
    replan_command: tuple[str, ...]
    expected_mixed_stdout_fragments: tuple[str, ...]
    expected_replan_stdout_fragments: tuple[str, ...]
    unexpected_replan_stdout_fragments: tuple[str, ...]
    expected_c_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class NodeSourceWatermarkBuildE2ETestCase:
    description: str
    project_name: str
    expected_source_versions_by_node: dict[str, tuple[str, ...]]
    expected_source_kinds_by_node: dict[str, tuple[str, ...]]
    expected_unknown_reasons_by_node: dict[str, tuple[str, ...]] = field(default_factory=dict)
    expected_absent_nodes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NodeSourceWatermarkWarningBuildE2ETestCase:
    description: str
    project_name: str
    models: dict[str, str]
    setup_build_command: tuple[str, ...]
    plan_command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    unexpected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_occurrences: dict[str, int] = field(default_factory=dict)
    setup_after_source_advance_commands: tuple[tuple[str, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PythonBuildE2ETestCase:
    """Test case for direct build Python-node behavior."""

    description: str
    expected_exit_code: int
    expected_execution_fragments: tuple[str, ...]
    expected_table_names: tuple[str, ...]
    expected_notify_text: str
    expected_fact_orders_rows: tuple[tuple[object, ...], ...]
    expected_asset_payload: dict[str, object]
    expected_asset_materialized: str


@dataclass(frozen=True)
class PythonPersistedResultBuildE2ETestCase:
    """Test case for direct build persisted Python-node results."""

    description: str
    expected_exit_code: int
    expected_consumed_text: str
    expected_success_values: tuple[int, ...]
    expected_failed_status: str


@dataclass(frozen=True)
class PythonLoaderPersistedResultBuildE2ETestCase:
    """Test case for persisted direct-mode loader result summaries."""

    description: str
    expected_exit_code: int
    expected_loader_text: str


@dataclass(frozen=True)
class PythonLoaderStatusResultBuildE2ETestCase:
    """Test case for persisted failed/skipped direct-mode loader results."""

    description: str
    project_name: str
    repo_files: dict[str, str]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PythonTargetIsolationBuildE2ETestCase:
    """Test case for target-scoped persisted Python-node reads."""

    description: str
    expected_exit_code: int
    expected_consumed_text: str
    expected_target_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class StandardPythonBuildHardeningE2ETestCase:
    """Test case for direct build Python lifecycle hardening behavior."""

    description: str
    project_name: str
    command: tuple[str, ...]
    repo_files: dict[str, str]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    expected_absent_tables: tuple[str, ...] = field(default_factory=tuple)
    expected_present_tables: tuple[str, ...] = field(default_factory=tuple)
    expected_markers: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    expected_absent_paths: tuple[str, ...] = field(default_factory=tuple)
    expected_json_assets: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    expected_json_status: str | None = None


@dataclass(frozen=True)
class PythonHooksBuildE2ETestCase:
    """Test case for build-time Python lifecycle hooks."""

    description: str
    expected_exit_code: int
    expected_orders_rows: tuple[tuple[object, ...], ...]
    expected_hook_log_rows: tuple[tuple[object, ...], ...]
    expected_output_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PythonHookFailureBuildE2ETestCase:
    """Test case for build-time Python lifecycle hook failures."""

    description: str
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    expected_present_tables: tuple[str, ...]
    expected_absent_tables: tuple[str, ...]
    model_sql: str | None = None


@dataclass(frozen=True)
class PythonHookSkipBuildE2ETestCase:
    """Test case for build-time Python lifecycle hook skips."""

    description: str
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    expected_present_tables: tuple[str, ...]
    expected_absent_tables: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class LongPythonHookNameBuildE2ETestCase:
    """Test case for CLI display of long Python hook names."""

    description: str
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    unexpected_output_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SnapshotPythonHooksBuildE2ETestCase:
    """Test case for snapshot builds with Python lifecycle hooks."""

    description: str
    expected_exit_code: int
    expected_snapshot_rows: tuple[tuple[object, ...], ...]
    expected_hook_log_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PythonHooksLifecycleMatrixBuildE2ETestCase:
    """Test case for build-time Python hooks across materialization kinds."""

    description: str
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    expected_hook_log_rows: tuple[tuple[object, ...], ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class VirtualPythonHooksBuildE2ETestCase:
    """Test case for virtual builds with Python lifecycle hooks."""

    description: str
    expected_exit_code: int
    expected_model_rows: tuple[tuple[object, ...], ...]
    expected_hook_log_rows: tuple[tuple[object, ...], ...]
    expected_identity_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DirectChangesOnlyBuildE2ETestCase:
    """Test case for direct build changes-only behavior."""

    description: str
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    unexpected_output_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_query_results: tuple[tuple[object, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VirtualBuildE2ETestCase:
    """Test case for virtual build e2e behavior."""

    description: str
    expected_build_fragments: tuple[str, ...]
    expected_plan_fragments: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]
    expected_ref_rows: tuple[tuple[object, ...], ...]
    expected_physical_version_count: int | None = None
    expected_default_plan_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_final_plan_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VirtualConcurrentBuildE2ETestCase:
    """Test case for concurrent virtual build e2e behavior."""

    description: str
    concurrency: int
    expected_model_count: int
    expected_build_fragments: tuple[str, ...]


@dataclass(frozen=True)
class VirtualSeedBuildE2ETestCase:
    """Test case for virtual seed build state behavior."""

    description: str
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]
    expected_changed_fragments: tuple[str, ...]
    expected_branch_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_physical_seed_count: int = 0


@dataclass(frozen=True)
class VirtualSeedGapE2ETestCase:
    """Test case for targeted virtual seed gap coverage."""

    description: str
    expected_fragments: tuple[str, ...] = field(default_factory=tuple)
    unexpected_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VirtualCustomMaterializationE2ETestCase:
    """Test case for virtual custom materialization behavior."""

    description: str
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]
    expected_ancestry_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class VirtualPythonBuildE2ETestCase:
    """Test case for virtual Python-node build behavior."""

    description: str
    project_name: str
    plan_command: tuple[str, ...]
    build_command: tuple[str, ...]
    expected_build_exit_code: int
    expected_plan_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_absent_plan_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_build_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_prepared_text: str | None = None
    expected_profile_text: str | None = None
    expected_source_profile_text: str | None = None
    expected_profile_exists: bool | None = None


@dataclass(frozen=True)
class VirtualPythonIdentityBuildE2ETestCase:
    """Test case for virtual Python identity persistence behavior."""

    description: str
    expected_state_identity_rows: tuple[tuple[object, ...], ...]
    expected_warehouse_fingerprint_table_count: int
    expected_changed_plan_fragments: tuple[str, ...]
    unexpected_changed_plan_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VirtualNodeResultStateE2ETestCase:
    """Test case for virtual node result state persistence behavior."""

    description: str
    expected_state_rows: tuple[tuple[object, ...], ...]
    expected_asset_payload: dict[str, object]
    expected_loader_text: str
    expected_history_text: str
    expected_warehouse_result_table_count: int
    expected_build_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VirtualNodeResultFailureStateE2ETestCase:
    """Test case for virtual failed node result state persistence behavior."""

    description: str
    project_name: str
    repo_files: dict[str, str]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_state_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class VirtualWaffleShopE2ETestCase:
    """Test case for full waffle shop virtual build behavior."""

    description: str
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]
    expected_view_names: tuple[str, ...]
    expected_function_names: tuple[str, ...]


@dataclass(frozen=True)
class VirtualBuildSelectionGuardE2ETestCase:
    """Test case for virtual build selection guard behavior."""

    description: str
    blocked_command: tuple[str, ...]
    expanded_command: tuple[str, ...]
    expected_blocked_fragments: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class VirtualSourceFreshnessBuildE2ETestCase:
    """Test case for virtual source freshness build behavior."""

    description: str
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_updated_rows: tuple[tuple[object, ...], ...]
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class VirtualPromoteE2ETestCase:
    """Test case for virtual promotion behavior."""

    description: str
    promote_command: tuple[str, ...]
    expected_promote_fragments: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]
    blocked_command: tuple[str, ...] = field(default_factory=tuple)
    expected_blocked_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VirtualRollbackE2ETestCase:
    """Test case for virtual rollback behavior."""

    description: str
    rollback_command: tuple[str, ...]
    expected_rollback_fragments: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]
    expected_checkpoint_count: int
    expected_exit_code: int = 0
    expected_stderr_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VirtualExplicitCheckpointRollbackE2ETestCase:
    """Test case for explicit checkpoint rollback behavior."""

    description: str
    rollback_command_prefix: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class VirtualPartialRollbackE2ETestCase:
    """Test case for partial rollback guard behavior."""

    description: str
    blocked_command: tuple[str, ...]
    allowed_command: tuple[str, ...]
    expected_blocked_stderr_fragments: tuple[str, ...]
    expected_allowed_stdout_fragments: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class ModelBackedCursorBuildE2ETestCase:
    """Test case for model-backed cursor build e2e regression coverage."""

    description: str
    repo_files: dict[str, str]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_table_names: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]
    expected_absent_runtime_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AppendCursorBuildE2ETestCase:
    """Test case for append cursor lower-bound behavior across reruns."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_runtime_sql_fragment: str
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class TimestampCursorBuildOverrideE2ETestCase:
    """Test case for timestamp cursor override behavior in sqb build."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_runtime_sql_fragment: str
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class SnapshotTimestampBuildE2ETestCase:
    """Test case for timestamp snapshot build behavior across CLI reruns."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_query: str
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotTimestampFailureBuildE2ETestCase:
    """Test case for timestamp snapshot build failures through the CLI."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotDmlFailureRollbackBuildE2ETestCase:
    """Test case for snapshot DML failure rollback behavior."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_initial_exit_code: int
    expected_failure_exit_code: int
    expected_error_fragments: tuple[str, ...]
    expected_query: str
    expected_rows_after_failure: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotCheckBuildE2ETestCase:
    """Test case for check snapshot build behavior across CLI reruns."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_query: str
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotHistoricalCheckBuildE2ETestCase:
    """Test case for historical check snapshot build behavior across CLI reruns."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_query: str
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotHistoricalTimestampBuildE2ETestCase:
    """Test case for historical timestamp snapshot build behavior across CLI reruns."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_query: str
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotCheckFailureBuildE2ETestCase:
    """Test case for check snapshot build failures through the CLI."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotFullRefreshFailureBuildE2ETestCase:
    """Test case for snapshot full-refresh safety failures through the CLI."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    initial_command: tuple[str, ...]
    full_refresh_command: tuple[str, ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotFullRefreshSuccessBuildE2ETestCase:
    """Test case for confirmed snapshot full-refresh behavior through the CLI."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    initial_command: tuple[str, ...]
    full_refresh_command: tuple[str, ...]
    expected_exit_code: int
    expected_query: str
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_refreshed_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotWaffleShopRerunBuildE2ETestCase:
    """Test case for a shallow multi-source snapshot rerun project."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql_by_round: tuple[tuple[str, ...], ...]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_query_results_by_round: tuple[
        tuple[tuple[str, tuple[tuple[object, ...], ...]], ...], ...
    ]


@dataclass(frozen=True)
class SnapshotSelectorBuildE2ETestCase:
    """Test case for snapshot dependency selector behavior through the CLI."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    excluded_downstream_command: tuple[str, ...]
    downstream_command: tuple[str, ...]
    expected_exit_code: int
    expected_snapshot_query: str
    expected_snapshot_rows_after_excluded_downstream: tuple[tuple[object, ...], ...]
    expected_downstream_query: str
    expected_downstream_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotHookBuildE2ETestCase:
    """Test case for snapshot hook behavior through the CLI."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_hook_query: str
    expected_hook_rows: tuple[tuple[object, ...], ...]
    expected_snapshot_query: str
    expected_snapshot_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotFailureConsistencyBuildE2ETestCase:
    """Test case for snapshot consistency after failure paths."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    command: tuple[str, ...]
    expected_initial_exit_code: int
    expected_failure_exit_code: int
    expected_output_fragments: tuple[str, ...]
    expected_snapshot_query: str
    expected_rows_after_failure: tuple[tuple[object, ...], ...]
    recovery_sql: tuple[str, ...] = field(default_factory=tuple)
    expected_rows_after_recovery: tuple[tuple[object, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TemplateExpressionsBuildE2ETestCase:
    """Test case for config-side template expression helpers."""

    description: str
    repo_files: dict[str, str]
    initial_seed_sql: str
    mutation_sql: tuple[str, ...]
    env: dict[str, str]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_runtime_sql_fragment: str
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class ExpressionSourceBuildE2ETestCase:
    """Test case for expression-backed source build coverage."""

    description: str
    repo_files: dict[str, str]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_table_names: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]
    expected_runtime_fragments: tuple[str, ...]


@dataclass(frozen=True)
class QueryChangeTrackingBuildE2ETestCase:
    """Test case for query-change tracking e2e regression coverage."""

    description: str
    repo_files: dict[str, str]
    build_command: tuple[str, ...]
    plan_command: tuple[str, ...]
    expected_exit_code: int
    expected_fingerprint_models: tuple[str, ...]
    expected_unchanged_models: tuple[str, ...]


@dataclass(frozen=True)
class CliFailureBuildE2ETestCase:
    """Test case for expected CLI validation/build failures."""

    description: str
    repo_files: dict[str, str]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stderr_fragments: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    pre_commands: tuple[tuple[str, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class QueryPropagationBuildE2ETestCase:
    """Test case for query-change propagation behavior across repeated CLI runs."""

    description: str
    repo_files: dict[str, str]
    initial_build_command: tuple[str, ...]
    plan_command: tuple[str, ...]
    mutation_file: str
    before_text: str
    after_text: str
    expected_exit_code: int
    expected_reasons: dict[str, str]
    expected_actions: dict[str, str] = field(default_factory=dict)
    expected_fingerprint_models: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SelectorSurfaceBuildE2ETestCase:
    """Test case for selector surface CLI behavior."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_fragments: tuple[str, ...]
    expected_stream: str
    pre_commands: tuple[tuple[str, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RuntimeArtifactPreservationBuildE2ETestCase:
    """Test case for runtime artifact preservation behavior."""

    description: str
    initial_command: tuple[str, ...]
    rerun_command: tuple[str, ...]
    expected_runtime_paths: tuple[str, ...]
    expected_exit_code: int
    expected_compiled_paths: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LifecycleCommandsBuildE2ETestCase:
    """Test case for core lifecycle command behavior."""

    description: str
    expected_exit_code: int
    expected_fresh_plan_fragments: tuple[str, ...]
    expected_test_fragment: str
    expected_audit_fragment: str
    expected_run_fragment: str
    expected_rerun_reasons: dict[str, str]
    expected_full_refresh_fragment: str
    expected_plan_ordered_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_build_ordered_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SchemaBackfillBuildE2ETestCase:
    """Test case for schema/backfill mutation behavior."""

    description: str
    mutate_model_file: str
    model_before_text: str
    model_after_text: str
    mutate_schema_file: str
    schema_before_text: str
    schema_after_text: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_reason: str
    expected_backfill_action: str | None = None
    expected_backfill_duration: str | None = None
    expected_warning_entries: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DirectChangesOnlyStateBuildE2ETestCase:
    """Test case for standard changes-only state/data behavior."""

    description: str
    project_name: str
    initial_amount_cents: int
    changed_amount_cents: int
    expected_initial_amount_dollars: float
    expected_changed_amount_dollars: float


@dataclass(frozen=True)
class DirectChangesOnlySeedBuildE2ETestCase:
    description: str
    project_name: str
    initial_seed_contents: str
    changed_seed_contents: str
    expected_plan_selected_count: int
    expected_amount_dollars: float


@dataclass(frozen=True)
class DirectSeedChangesOnlyGapE2ETestCase:
    description: str
    project_name: str
    expected_plan_fragment: str = ""
    expected_seed_payload: tuple[dict[str, object], ...] = field(default_factory=tuple)
    expected_fact_order_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_customer_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DirectReuseFromBuildE2ETestCase:
    description: str
    project_name: str
    expected_prod_build_exit_code: int
    expected_dev_build_exit_code: int


@dataclass(frozen=True)
class MixedTimestampGrainBuildE2ETestCase:
    """Test case for mixed timestamp grain replay behavior."""

    description: str
    repo_files: dict[str, str]
    initial_command: tuple[str, ...]
    rerun_command: tuple[str, ...]
    expected_exit_code: int
    expected_window_fragment: str
    expected_row_count: int


@dataclass(frozen=True)
class AuditFailureBuildE2ETestCase:
    """Test case for audit failure CLI behavior."""

    description: str
    repo_files: dict[str, str]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_failure_fragment: str
    expected_retained_relation_fragment: str


@dataclass(frozen=True)
class CompileJsonBuildE2ETestCase:
    """Test case for compile JSON behavior."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_model_names: tuple[str, ...]
    expected_sql_fragments: tuple[str, ...]
    expected_warning_count: int = 0
    expected_diagnostic_codes: tuple[str, ...] = field(default_factory=tuple)
    expected_pre_hooks: tuple[dict[str, object], ...] = field(default_factory=tuple)
    expected_post_hooks: tuple[dict[str, object], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DagJsonBuildE2ETestCase:
    """Test case for dag JSON behavior."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_project_name: str
    expected_node_ids: tuple[str, ...]
    expected_edge_pairs: tuple[tuple[str, str], ...]
    expected_check_ids: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PlanCommandBuildE2ETestCase:
    """Test case for plan command surface behavior."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_fragments: tuple[str, ...]
    expected_stream: str


@dataclass(frozen=True)
class VirtualModeGuardBuildE2ETestCase:
    description: str
    project_toml: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_error_fragment: str


@dataclass(frozen=True)
class RemoveColumnSemanticsBuildE2ETestCase:
    """Test case for remove-column mutation semantics."""

    description: str
    mutate_file: str
    before_text: str
    after_text: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_reason: str
    expected_backfill_action: str
    expected_backfill_duration: str | None
    expected_warning_count: int
