"""Test case types for compile command performance guards."""

from __future__ import annotations

from dataclasses import dataclass


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
    expected_max_rss_bytes: int
    expected_max_cache_bytes: int
    expected_cold_fingerprint: str
    expected_leaf_edit_fingerprint: str
    expected_macro_edit_fingerprint: str
    expected_project_config_fingerprint: str


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
