"""Test case types for compile command performance guards."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest

from tests.integration.src.sqlbuild.compiler.pipeline._test_types import PreparedCompile

if TYPE_CHECKING:
    from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import CompileReuseRun


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
    edited_env: dict[str, str] = field(default_factory=dict)
    expected_failure: bool = False
    expected_output_change: bool = True
    expected_rewarmed_analysis_cache_misses: int = 0


@dataclass(frozen=True)
class CompileCacheDisabledTestCase:
    """One supported control that disables compile-cache reads and writes."""

    description: str
    compile_args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    edit: Callable[[Path], None] = lambda _root: None
    expected_analysis_cache_counts: tuple[int, int] = (0, 0)
    expected_analysis_databases: tuple[Path, ...] = ()


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
class RequiredDescriptionExactOutputCase:
    description: str
    files: tuple[tuple[str, str], ...]
    expected_diagnostics: tuple[tuple[str, str, str, int, int], ...]
    expected_help: tuple[str, ...]


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


@dataclass(frozen=True)
class CompileReuseInvalidationTestCase:
    """One compile input change that must make the stored compile miss."""

    description: str
    edit: Callable[[Path], None] = lambda _project_dir: None
    edited_env: dict[str, str] = field(default_factory=dict)
    edited_args: tuple[str, ...] = ()
    expected_returncode: int = 0
    expected_rewarm_hit: bool = True


@dataclass(frozen=True)
class CompileReuseHitTestCase:
    """One change outside the compile inputs that must still reuse the stored compile."""

    description: str
    edit: Callable[[Path], None]
    edited_env: dict[str, str] = field(default_factory=dict)
    expected_reused: bool = True


@dataclass(frozen=True)
class CompileReuseBypassTestCase:
    """One control or input that must always run the full compile."""

    description: str
    edit: Callable[[Path], None] = lambda _project_dir: None
    compile_args: tuple[str, ...] = ()
    global_args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    expected_stored_entries: int = 0


@dataclass(frozen=True)
class CompileReuseCorruptEntryTestCase:
    """One way a stored compile can be damaged on disk."""

    description: str
    corrupt: Callable[[Path], None]
    expected_fallback_reused: bool = False
    expected_restored_reused: bool = True


@dataclass(frozen=True)
class CompileReuseReplayTestCase:
    """One compile whose replay must reproduce output, notes, and exit code."""

    description: str
    compile_args: tuple[str, ...]
    expected_returncode: int
    expected_note_prefix: str = "note:"


@dataclass(frozen=True)
class CompileReuseRedirectTestCase:
    """A compile whose stdout is redirected into a file inside the project."""

    description: str
    report_name: str
    expected_hit_counts: tuple[int, int]


@dataclass(frozen=True)
class CompileReuseEventTestCase:
    """A lifecycle sink that must still receive invocation events on a reuse hit."""

    description: str
    sink_name: str
    expected_event_types: tuple[str, ...]


@dataclass(frozen=True)
class CompileReuseTimingsTestCase:
    """The compile_timings object a reuse hit reports in place of the stored timings."""

    description: str
    expected_timing_names: frozenset[str]


@dataclass(frozen=True)
class CompileReuseProviderSettingsTestCase:
    """A provider settings input change that must miss and match a full compile."""

    description: str
    edited_env: dict[str, str]
    edit: Callable[[Path], None] = lambda _project_dir: None
    expected_returncode: int = 0
    expected_rewarm_hit: bool = True


@dataclass(frozen=True)
class CompileReuseConcurrentWriterTestCase:
    """Another writer touching compiled artifacts between this compile's write and store."""

    description: str
    other_write: Callable[[Path], None]
    expected_stored_entries: int
    expected_rerun_reused: bool


@dataclass(frozen=True)
class CompileReuseLargeFileTestCase:
    """A large data file that reuse must not read unless its stat identity moves."""

    description: str
    size_bytes: int
    relative_path: str
    expected_reads: tuple[int, int, int, int, int]
    expected_reused: tuple[bool, bool, bool, bool, bool]


@dataclass(frozen=True)
class CompileReuseStoreFailureTestCase:
    """An unexpected error while storing a finished compile."""

    description: str
    error: BaseException
    expected_returncode: int = 0
    expected_stored_entries: int = 0
    expected_raised: type[BaseException] | None = None


@dataclass(frozen=True)
class IncrementalEditStep:
    """One authored edit, the command run over it before its compile, and whether it replays."""

    description: str
    edit: Callable[[Path], None]
    between: Callable[[Path], None]
    expected_replayed: bool = False


@dataclass(frozen=True)
class IncrementalEditSequenceTestCase:
    """Edits applied in order, each compiled incrementally and compared with --no-cache."""

    description: str
    steps: tuple[IncrementalEditStep, ...]
    expected_matches_uncached: bool = True


@dataclass(frozen=True)
class RandomEditChainTestCase:
    """A seeded random chain of edits over a generated project."""

    description: str
    seed: int
    model_count: int
    step_count: int
    expected_matches_uncached: bool = True


@dataclass(frozen=True)
class BrokenEditInvalidationTestCase:
    """A cache invalidation deliberately broken, and an edit whose output it must change."""

    description: str
    edit: Callable[[Path], None]
    sabotage: Callable[[pytest.MonkeyPatch], None]
    expected_matches_uncached: bool


@dataclass(frozen=True)
class ExternalModuleEditTestCase:
    """An outside module a macro imports while rendering, rewritten in place after a compile."""

    description: str
    initial_value: str
    edited_value: str
    expected_matches_uncached: bool
    expected_compiled_value: str


@dataclass(frozen=True)
class SqlTestScanStoreTestCase:
    """A change between two compiles, and how many stored SQL-test scans it must invalidate."""

    description: str
    change: Callable[[Path, pytest.MonkeyPatch], None]
    expected_rescans: int
    arrange: Callable[[pytest.MonkeyPatch], None] = lambda _monkeypatch: None
    expected_matches_uncached: bool = True


@dataclass(frozen=True)
class RetiredCompilerCacheTestCase:
    """A compile over a project holding cache files older releases wrote."""

    description: str
    compile_args: tuple[str, ...]
    expected_removed: bool


@dataclass(frozen=True)
class DenseBatchedPreparationTestCase:
    description: str
    model_count: int
    expected_exit_code: int


type DensePreparedCompile = PreparedCompile


@dataclass(frozen=True)
class SharedCacheKeyTestCase:
    """A model analysis schedule under which two models share one analysis cache key."""

    description: str
    schedule: Callable[[pytest.MonkeyPatch], None]
    expected_matches_uncached: bool = True


@dataclass(frozen=True)
class CompilerEngineParityTestCase:
    """Two engines compiling separate copies of one project."""

    description: str
    left_engine: str
    right_engine: str
    expected_engines: tuple[str, str]
    expected_exit_codes: tuple[int, int]


@dataclass(frozen=True)
class NativeTypeSystemTestCase:
    """Python and preview compiles of one project whose contracts compare type spellings."""

    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_report_text: str


@dataclass(frozen=True)
class NativeAnalysisSeamTestCase:
    """Every engine compiling a copy of one project while the analysis stage seams are recorded."""

    description: str
    expected_preview_returns: dict[str, list[object]]


@dataclass(frozen=True)
class CompilerEngineMacroParityTestCase:
    """Two engines compiling separate copies of one macro-heavy project."""

    description: str
    files: dict[str, str]
    expected_exit_codes: tuple[int, int]
    expected_compiled_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompilerEngineStoreTestCase:
    """A sequence of engine compiles in one project and which of them reuse a stored compile."""

    description: str
    engines: tuple[str, ...]
    expected_reused: tuple[bool, ...]
    expected_python_stores: tuple[str, ...]
    expected_native_stores: tuple[str, ...]


@dataclass(frozen=True)
class CompilerEngineRulesStoreTestCase:
    """Compile plus Rules under each engine and the store files each engine must own."""

    description: str
    rules_selector: str
    stores: tuple[str, ...]
    native_marker: str
    expected_python_files: tuple[str, ...]
    expected_native_files: tuple[str, ...]


@dataclass(frozen=True)
class CompilerEngineTierStoreTestCase:
    """Alternating compiles under two native tiers and the stores each tier must own alone."""

    description: str
    engines: tuple[str, ...]
    expected_reused: tuple[bool, ...]
    expected_first_engine_stores: tuple[str, ...]
    expected_second_engine_stores: tuple[str, ...]


@dataclass(frozen=True)
class NativeModelConfigParityTestCase:
    """Authored model config compiled by two engines that must report and write the same."""

    description: str
    project_files: dict[str, str]
    project_config_replacements: tuple[tuple[str, str], ...]
    environment: dict[str, str]
    engines: tuple[str, str]
    expected_exit_codes: tuple[int, int]
    expected_report_text: str


@dataclass(frozen=True)
class ReplaceableReferenceCallTestCase:
    """A compiler engine that must build double-quoted reference calls end to end."""

    description: str
    engine: str
    expected_total_cents: str


@dataclass(frozen=True)
class RejectedReferenceCallTestCase:
    """A reference call form compile cannot replace and the error it must report first."""

    description: str
    engine: str
    staging_from: str
    mart_from: str
    expected_diagnostics: tuple[tuple[str, str, str, int, int, str], ...]


@dataclass(frozen=True)
class NativeModelLoopParityTestCase:
    """Models whose declarations two engines must resolve, report and write the same way."""

    description: str
    project_files: dict[str, str]
    engines: tuple[str, str]
    expected_exit_codes: tuple[int, int]
    expected_report_text: str


@dataclass(frozen=True)
class NativeDeclarationErrorTestCase:
    """A failing project whose declaration error both engines must report the same way."""

    description: str
    project_files: dict[str, str]
    expected_report_text: str
    expected_macro_calls: int


@dataclass(frozen=True)
class NativeConfigErrorTestCase:
    """A failing project whose model config error both engines must report the same way."""

    description: str
    project_files: dict[str, str]
    expected_report_text: str
    expected_macro_calls: int
    expected_python_fallbacks: list[str]


@dataclass(frozen=True)
class DeclarationErrorLifecycleTestCase:
    """A failing project whose invocation lifecycle every engine must report the same way."""

    description: str
    project_files: dict[str, str]
    expected_error_types: tuple[str, ...]


@dataclass(frozen=True)
class MacroReferenceCallStoreTestCase:
    """Repeated compiles of models sharing a macro that returns a rejected reference call."""

    description: str
    engine: str
    expected_logged_calls: tuple[int, ...]


@dataclass(frozen=True)
class MacroCallStoreEditStep:
    """One edit compiled with the macro call store, and the executions it expects."""

    description: str
    edit: Callable[[Path], object]
    expected_logged_calls: int
    args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MacroCallStoreEditSequenceTestCase:
    """Edits applied in order, each compiled with the macro call store and with --no-cache."""

    description: str
    project_reuse: bool
    steps: tuple[MacroCallStoreEditStep, ...]
    expected_matches_uncached: bool = True


@dataclass(frozen=True)
class BrokenMacroCallStoreKeyTestCase:
    """An edit the store key no longer covers, which the --no-cache oracle must catch."""

    description: str
    edit: Callable[[Path], None]
    expected_matches_uncached: bool


@dataclass(frozen=True)
class EngineMacroCallGateTestCase:
    """Repeated full compiles under one engine and whether the bridge and store took part."""

    description: str
    engine: str
    expected_logged_calls: tuple[int, ...]
    expected_store_files: tuple[str, ...]


class StaleStoreArrangement(NamedTuple):
    """What an arrangement step may use to compile and edit before the fresh-process check."""

    project_dir: Path
    extlib: Path
    monkeypatch: pytest.MonkeyPatch
    capsys: pytest.CaptureFixture[str]


@dataclass(frozen=True)
class StaleMacroModuleStoreTestCase:
    """An outside module a macro imported, edited after this process imported it."""

    description: str
    arrange: Callable[[StaleStoreArrangement], None]
    compile_afresh: Callable[[StaleStoreArrangement], CompileReuseRun]
    expected_flavor: str


@dataclass(frozen=True)
class SecondCompileStoreTestCase:
    """Two compiles in one process; the second must run its macros without the store."""

    description: str
    expected_second_matches_first: bool


@dataclass(frozen=True)
class DeepHeaderNestingCompileCase:
    description: str
    engine: str
    path: str
    prefix: str
    suffix: str
    depth: int
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DeepCallNestingCompileCase:
    description: str
    depth: int
    engines: tuple[str, ...]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DollarQuotedProjectVarCompileCase:
    description: str
    engine: str
    model_sql: str
    expected_fragment: str
