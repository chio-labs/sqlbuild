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
class RemoveColumnSemanticsBuildE2ETestCase:
    """Test case for remove-column mutation semantics."""

    description: str
    mutate_file: str
    before_text: str
    after_text: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_reason: str
    expected_warning_fragment: str
