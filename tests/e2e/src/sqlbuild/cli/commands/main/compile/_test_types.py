"""Test case types for compile command performance guards."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SourceSemanticBindingCase:
    description: str
    command: str
    expected_code: str = "B002"


@dataclass(frozen=True)
class RelationStubNameCase:
    description: str
    stub_cte_name: str
    expected_downstream_type: str
    expected_ghost_column_diagnostics: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class SemanticCorpusCase:
    description: str
    category: str
    repo_files: dict[str, str]
    expected_exit_code: int
    expected_codes: tuple[str, ...]
    pending_native: bool


@dataclass(frozen=True)
class VariedCompileCacheTestCase:
    description: str
    model_count: int
    expected_cold_max_seconds: float
    expected_warm_max_seconds: float
    expected_edit_max_seconds: float
    expected_max_rss_bytes: int
    expected_min_operator_shapes: int
    expected_min_component: int
    expected_min_depth: int
    expected_max_depth: int
    expected_min_leaves: int
    expected_max_leaves: int
    expected_min_array_models: int
    expected_min_window_models: int
    expected_fingerprints: tuple[str, str, str, str]


@dataclass(frozen=True)
class CompilePerformanceGuardTestCase:
    description: str
    model_count: int
    expected_max_seconds: float


@dataclass(frozen=True)
class CompileScalingGuardTestCase:
    description: str
    model_count: int
    small_scan_event_lines_per_model: int
    large_scan_event_lines_per_model: int
    expected_min_small_sql_bytes: int
    expected_min_large_sql_bytes: int
    expected_small_scan_events: int
    expected_large_scan_events: int
    expected_max_seconds: float
    expected_max_scaling_ratio: float


@dataclass(frozen=True)
class DbtShapedCompilePerformanceGuardTestCase:
    description: str
    model_count: int
    expected_min_sql_bytes: int
    expected_max_sql_bytes: int
    expected_max_seconds: float
    expected_warm_max_seconds: float


@dataclass(frozen=True)
class SqlTestHeavyCompilePerformanceGuardTestCase:
    description: str
    model_count: int
    test_count: int
    chain_depth: int
    fixture_row_count: int
    expected_min_compiled_test_bytes: int
    expected_max_seconds: float
    expected_warm_max_seconds: float
    expected_edit_max_seconds: float


@dataclass(frozen=True)
class LayeredProductionCompilePerformanceGuardTestCase:
    description: str
    model_count: int
    source_count: int
    seed_count: int
    function_count: int
    macro_count: int
    test_count: int
    expected_audit_count: int
    expected_hook_count: int
    expected_min_model_sql_bytes: int
    expected_max_model_sql_bytes: int
    expected_min_compiled_test_bytes: int
    expected_max_compiled_test_bytes: int
    expected_cold_max_seconds: float
    expected_warm_max_seconds: float
    expected_edit_max_seconds: float
    expected_config_edit_max_seconds: float


@dataclass(frozen=True)
class LayeredProductionCompileTestCase:
    description: str
    model_count: int
    source_count: int
    seed_count: int
    function_count: int
    macro_count: int
    test_count: int
    audit_count: int
    expected_diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True)
class SemanticCompilePerformanceGuardTestCase:
    description: str
    model_count: int
    source_count: int
    seed_count: int
    function_count: int
    macro_count: int
    test_count: int
    audit_count: int
    expected_min_declared_columns: int
    expected_max_declared_columns: int
    expected_min_model_sql_bytes: int
    expected_max_model_sql_bytes: int
    expected_min_compiled_test_bytes: int
    expected_max_compiled_test_bytes: int
    expected_cold_max_seconds: float
    expected_warm_max_seconds: float


@dataclass(frozen=True)
class FreshProcessCompilePerformanceGuardTestCase:
    description: str
    model_count: int
    source_count: int
    seed_count: int
    function_count: int
    macro_count: int
    test_count: int
    audit_count: int
    expected_max_wall_seconds: float
    expected_max_rss_bytes: int
    expected_semantic_fingerprint: str


@dataclass(frozen=True)
class FreshProcessCompileCachePerformanceGuardTestCase:
    description: str
    model_count: int
    source_count: int
    seed_count: int
    function_count: int
    macro_count: int
    test_count: int
    audit_count: int
    expected_cold_max_wall_seconds: float
    expected_warm_max_wall_seconds: float
    expected_edit_max_wall_seconds: float
    expected_max_warm_to_cold_ratio: float
    expected_max_edit_to_cold_ratio: float
    expected_max_cache_write_cpu_overhead_ratio: float
    expected_max_cache_write_wall_overhead_ratio: float
    expected_max_rss_bytes: int
    expected_max_cache_bytes: int
    expected_cold_fingerprint: str
    expected_leaf_edit_fingerprint: str
    expected_macro_edit_fingerprint: str
    expected_project_config_fingerprint: str
    macro_call_interval: int
    scoped_macros: bool
    expected_macro_edit_misses: int


@dataclass(frozen=True)
class NamespaceCompileTestCase:
    description: str
    repo_files: dict[str, str]
    expected_exit_code: int
    expected_stderr_fragment: str


@dataclass(frozen=True)
class PathDefaultCompileTestCase:
    description: str
    repo_files: dict[str, str]
    expected_exit_code: int
    expected_stderr_fragment: str


@dataclass(frozen=True)
class PythonProjectLayoutCompileTestCase:
    description: str
    repo_files: dict[str, str]
    expected_exit_code: int
    expected_stderr_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompileSelectionTestCase:
    description: str
    selection_args: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    unexpected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DeepSqlAnalysisCompileTestCase:
    description: str
    function_depth: int
    expected_stdout_fragment: str


@dataclass(frozen=True)
class DenseCompileGuardTestCase:
    description: str
    model_count: int
    expected_max_wall_seconds: float
    expected_max_rss_bytes: int
    expected_fingerprint: str


@dataclass(frozen=True)
class DenseWarmEditCompileGuardTestCase:
    description: str
    model_count: int
    edited_model_index: int
    expected_warm_max_seconds: float
    expected_edit_max_seconds: float
    expected_max_rss_bytes: int
    expected_cold_fingerprint: str
    expected_edit_fingerprint: str
    expected_edit_rule_cache_misses: int


@dataclass(frozen=True)
class RuleGatedTestDiagnosticsTestCase:
    description: str
    filler_model_count: int
    extra_args: tuple[str, ...]
    expected_diagnostics: tuple[tuple[str, str, str], ...]
    expected_text_lines: tuple[str, ...]


@dataclass(frozen=True)
class EmptyInputTestRuleCompileTestCase:
    description: str
    select: tuple[str, ...]
    expected_diagnostics: frozenset[tuple[str, str, str]]


@dataclass(frozen=True)
class EmptyInputTestRuleOptionErrorTestCase:
    description: str
    allowed_tests_toml: str
    expected_error: str


@dataclass(frozen=True)
class EmptyInputTestRuleCacheTestCase:
    description: str
    replacement_mock: str
    expected_first_codes: tuple[str, ...]
    expected_second_codes: tuple[str, ...]


@dataclass(frozen=True)
class TypeProofRuleCompileTestCase:
    description: str
    project_toml: str
    extra_args: tuple[str, ...]
    expected_returncode: int
    expected_rule_findings: int
    expected_note_count: int


@dataclass(frozen=True)
class FactoryModuleNodePlanTestCase:
    description: str
    repo_files: dict[str, str]
    expected_python_node_names: tuple[str, ...]


@dataclass(frozen=True)
class UnrelatedPythonPackageBuildTestCase:
    description: str
    unrelated_files: dict[str, str]
    repo_files: dict[str, str]
    expected_build_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DiagnosticPerformanceCase:
    description: str
    depth: int = 100
    width: int = 32
    expected_max_wall_seconds: float = 20.0
    expected_timeout_seconds: float = 65.0
    diagnostic_count: int = 100


@dataclass(frozen=True)
class InspectionCommandPerformanceGuardTestCase:
    description: str
    sqb_args: tuple[str, ...]
    expected_fragments: tuple[str, ...]
    expected_max_output_lines: int
    expected_max_wall_seconds: float
    expected_max_rss_bytes: int


@dataclass(frozen=True)
class PlanComparedToCompileGuardTestCase:
    description: str
    expected_max_compile_ratio: float
    expected_max_plan_wall_seconds: float
    expected_max_rss_bytes: int


@dataclass(frozen=True)
class PlanScalingGuardTestCase:
    description: str
    small_model_count: int
    expected_max_linear_factor: float


@dataclass(frozen=True)
class PlanPhaseScalingGuardTestCase:
    description: str
    small_model_count: int
    runs: int
    expected_phases: tuple[str, ...]
    expected_max_linear_factor: float
    expected_max_large_phase_seconds: float


@dataclass(frozen=True)
class BuildPerformanceGuardTestCase:
    description: str
    expected_max_wall_seconds: float
    expected_max_rss_bytes: int


@dataclass(frozen=True)
class ExistingStatePlanGuardTestCase:
    description: str
    edited_models: tuple[str, ...]
    renamed_models: tuple[tuple[str, str], ...]
    expected_query_changed: tuple[str, ...]
    expected_migrations: tuple[tuple[str, str, str], ...]
    expected_max_wall_seconds: float
    expected_max_rss_bytes: int


@dataclass(frozen=True)
class CompileCacheInvalidationTestCase:
    """One authored input edit applied after a warm compile-cache run."""

    description: str
    edit: Callable[[Path], None]
    setup: Callable[[Path], None] = lambda _root: None
    edited_env: dict[str, str] = field(default_factory=dict)
    edited_compile_args: tuple[str, ...] = ()
    expected_failure: bool = False
    expected_output_change: bool = True
    expected_rewarmed_fact_cache_misses: int = 0


@dataclass(frozen=True)
class AttachmentCacheReuseTestCase:
    """One project change after a warm compile and the expected model attachment reuse."""

    description: str
    edit: Callable[[Path], None]
    expected_attachment_counts: tuple[int, int, int]
    setup: Callable[[Path], None] = lambda _root: None
    initial_env: dict[str, str] = field(default_factory=dict)
    edited_env: dict[str, str] = field(default_factory=dict)
    expected_failure: bool = False


@dataclass(frozen=True)
class AttachmentRunIdTestCase:
    """One model whose hook renders the per-invocation run id."""

    description: str
    model_path: str
    model_sql: str
    expected_warm_attachment_counts: tuple[int, int, int]


@dataclass(frozen=True)
class AttachmentDiagnosticReplayTestCase:
    """Project files whose attachment reports diagnostics a cache hit must replay."""

    description: str
    files: dict[str, str]
    expected_diagnostic_codes: tuple[str, ...]
    expected_warm_attachment_counts: tuple[int, int, int]


@dataclass(frozen=True)
class AttachmentReferencePolicyTestCase:
    """A replayed diagnostic whose presence follows the explicit-reference policy."""

    description: str
    files: dict[str, str]
    relax: Callable[[Path], None]
    restore: Callable[[Path], None]
    expected_strict_codes: tuple[str, ...]
    expected_relaxed_codes: tuple[str, ...]


@dataclass(frozen=True)
class CompileCacheDisabledTestCase:
    """One supported control that disables compile-cache reads and writes."""

    description: str
    compile_args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    edit: Callable[[Path], None] = lambda _root: None
    expected_fact_cache_counts: tuple[int, int] = (0, 0)
    expected_fact_databases: tuple[Path, ...] = ()


@dataclass(frozen=True)
class FunctionHeaderKeyCompileCase:
    description: str
    repo_files: dict[str, str]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class FunctionNameCompileTestCase:
    description: str
    project_toml: str
    query_sql: str
    expected_exit_code: int
    expected_diagnostics: tuple[tuple[str, str, int, int], ...]


@dataclass(frozen=True)
class ModelHeaderKeyCompileCase:
    description: str
    repo_files: dict[str, str]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ResourceSqlValidationCase:
    description: str
    files: tuple[tuple[str, str], ...]
    expected_diagnostics: tuple[tuple[str, str, str, int], ...]


@dataclass(frozen=True)
class ResourceSqlOptOutCase:
    description: str
    files: tuple[tuple[str, str], ...]
    flags: tuple[str, ...]
    expected_diagnostics: tuple[tuple[str, str, int], ...]
    expected_returncode: int = 0


@dataclass(frozen=True)
class ResourceSqlHelpCase:
    description: str
    files: tuple[tuple[str, str], ...]
    expected_diagnostics: tuple[tuple[str, str, str | None], ...]


@dataclass(frozen=True)
class TypeFindingLocationCase:
    description: str
    adapter: str
    query_sql: str
    expected_diagnostics: tuple[tuple[str, str, int, int], ...]


@dataclass(frozen=True)
class RequireSqlAnalysisCase:
    description: str
    repo_files: tuple[tuple[str, str], ...]
    command: tuple[str, ...]
    expected_returncode: int
    expected_diagnostics: tuple[tuple[str, str | None, int | None], ...]
    expected_text_fragments: tuple[str, ...]


@dataclass(frozen=True)
class SetOperationModel:
    description: str
    name: str
    query_sql: str
    expected_row_count: int | None = None


@dataclass(frozen=True)
class SetOperationLifecycleTestCase:
    description: str
    models: tuple[SetOperationModel, ...]
    expected_column_count: int
    expected_diagnostics: tuple[tuple[str, str], ...]
    expected_rule_summary: str
    expected_indented_set_operation_lines: tuple[str, ...]


@dataclass(frozen=True)
class SetOperationArityMismatchTestCase:
    description: str
    models: tuple[SetOperationModel, ...]
    expected_exit_code: int
    expected_diagnostics: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class UnionFixtureCompileScalingTestCase:
    description: str
    sql_test_count: int
    small_fixture_rows: int
    large_fixture_rows: int
    measured_runs: int
    expected_sql_tests: int
    expected_errors: int
    expected_max_scaling_ratio: float
    input_fixture_row_separator: str = " UNION ALL\n"


@dataclass(frozen=True)
class RequiredDescriptionCase:
    description: str
    missing_files: tuple[tuple[str, str], ...]
    described_files: tuple[tuple[str, str], ...]
    expected_diagnostic: tuple[str, str, int]
    expected_message: str
    expected_help_fragments: tuple[str, ...]


@dataclass(frozen=True)
class RequiredDescriptionAggregateCase:
    description: str
    files: tuple[tuple[str, str], ...]
    expected_codes: frozenset[str]
    expected_kinds: frozenset[str]


@dataclass(frozen=True)
class RequiredDescriptionPlanCase:
    description: str
    model_sql: str
    expected_returncode: int
    expected_stderr_fragment: str


@dataclass(frozen=True)
class PathDefaultDescriptionCase:
    description: str
    model_files: tuple[tuple[str, str], ...]
    expected_returncode: int
    expected_diagnostics: tuple[object, ...]
    expected_descriptions: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class FormatDescriptionResolutionE2ECase:
    description: str
    extra_files: tuple[tuple[str, str], ...]
    expected_returncode: int
    expected_faults: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class EarlyLintCompileTestCase:
    """A rules-enabled project and the diagnostics compile must report for it."""

    description: str
    order_totals_sql: str
    expected_exit_code: int
    expected_diagnostics: tuple[tuple[str, str, int, int], ...]
