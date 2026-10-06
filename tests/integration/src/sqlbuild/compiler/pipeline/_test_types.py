from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scripts.cold_compile_performance.models import RandomDagProject
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter


@dataclass(frozen=True)
class ExpressionMemoCase:
    description: str
    expression: str
    expected_analysis_calls: int = 1


@dataclass(frozen=True)
class ExpressionBatchCase:
    description: str
    orders_expression: str
    customers_expression: str
    expected_batches: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ShapeCacheCase:
    description: str
    sql: str
    expected_columns: int = 2
    expected_star: bool = True


@dataclass(frozen=True)
class IdentifierBindingCase:
    description: str
    dialect: str
    projection: str
    reference: str
    expected_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationCacheCase:
    description: str
    enabled: bool
    expected_hits: int
    expected_bypasses: int


@dataclass(frozen=True)
class NativeCatalogCase:
    description: str
    sql: str
    expected_codes: tuple[str, ...] = ()
    spelling: str = "MiSsPeLlEd"
    expected_sql: str = "SELECT * FROM __sqlbuild_table_function_table_fn__orders"


@dataclass(frozen=True)
class SemanticCompileCase:
    description: str
    upstream: str
    downstream: str
    expected_code: str | None
    header: str = "MODEL (description 'Test model.', materialized view);\n"
    expected_diagnostic_count: int = 1
    expected_column: int | None = None


@dataclass(frozen=True)
class DiagnosticUxCase:
    description: str
    edits: tuple[tuple[str, str, str], ...]
    extra_files: tuple[tuple[str, str], ...] = ()
    expected_errors: int = 1
    expected_fragments: tuple[str, ...] = ()
    expected_partial: bool = True


@dataclass(frozen=True)
class ColumnSuggestionCase:
    description: str
    name: str
    columns: tuple[str, ...]
    expected_match: str | None


@dataclass(frozen=True)
class SemanticTriageCase:
    description: str
    column_type: str = "DATE"
    cursor_type: str = "timestamp"
    setting: str = ""
    expected_codes: tuple[str, ...] = ()
    independent_sql: str = ""
    root_contract: str = ""


@dataclass(frozen=True)
class SnowflakeSemanticReleaseCase:
    description: str
    sql: str
    expected_codes: tuple[str, ...] = ()
    expected_exit_code: int = 0


@dataclass(frozen=True)
class SnowflakeOutputInferenceCase:
    description: str
    sql: str
    expected_type: str | None = None


@dataclass(frozen=True)
class RulesPipelineIntegrationTestCase:
    """One configured Rules failure in the shared planning compiler."""

    description: str
    expected_error_pattern: str
    expected_connection_calls: int


@dataclass(frozen=True)
class AuditFactoryCompileIntegrationTestCase:
    description: str
    expected_audit_count: int


@dataclass(frozen=True)
class MeasurementCompileIntegrationTestCase:
    description: str
    expected_minimum_samples: int
    expected_severity: str


@dataclass(frozen=True)
class MeasurementCompileErrorIntegrationTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class SemanticBindingClauseIntegrationTestCase:
    description: str
    query_sql: str
    missing_column: str
    expected_error_code: str = "B002"
    expected_exit_code: int = 1


@dataclass(frozen=True)
class SemanticBindingIntegrationTestCase:
    description: str
    expected_exit_code: int


@dataclass(frozen=True)
class SourceContractDefaultIntegrationTestCase:
    description: str
    source_contract_yaml: str
    expected_exit_code: int
    expected_output_fragment: str
    expected_absent_output_fragment: str


@dataclass(frozen=True)
class ExpectedModelEntry:
    description: str
    expected_resolved_sql_fragment: str
    expected_logical_ddl_fragment: str
    expected_manifest_compiled_code_fragment: str


@dataclass(frozen=True)
class RunCompilePipelineIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_models: dict[str, ExpectedModelEntry] = field(default_factory=dict)
    expected_model_count: int = 0
    expected_seed_count: int = 0
    expected_manifest_node_count: int = 0
    expected_declaration_usages: tuple[str, ...] = ()
    warehouse_setup_sql: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectionLineageIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    select: tuple[str, ...]
    expected_selected_names: frozenset[str]
    expected_unselected_names: frozenset[str]


@dataclass(frozen=True)
class MacroLoadCountIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_macro_import_count: int
    expected_declaration_resolution_count: int


@dataclass(frozen=True)
class MacroCompositionIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    macro_name: str
    expected_dependencies: tuple[str, ...]
    expected_declaration_resolution_count: int


@dataclass(frozen=True)
class MacroDeclarationContextErrorTestCase:
    description: str
    project_files: dict[str, str]
    expected_error_fragment: str


@dataclass(frozen=True)
class MacroDeclarationResourceTestCase:
    description: str
    expected_model_sql_fragment: str
    expected_test_sql_fragment: str
    expected_audit_sql_fragment: str


@dataclass(frozen=True)
class MacroDeclarationRenderingTestCase:
    description: str
    adapter_name: str
    adapter_factory: Callable[[], BaseAdapter]
    expected_sql: str


@dataclass(frozen=True)
class GroupedDeclarationCompileTestCase:
    """Compilation expectation for declarations under one _sqlbuild group."""

    description: str
    project_files: dict[str, str]
    expected_sql: str


@dataclass(frozen=True)
class MacroTestDiscoveryIntegrationTestCase:
    """Compilation expectation for a macro test stored in its mirrored path."""

    description: str
    project_files: dict[str, str]
    expected_test_name: str
    expected_macro_name: str


@dataclass(frozen=True)
class SqlTestProductionScopeIntegrationTestCase:
    """Expected production and helper declaration visibility for one SQL test."""

    description: str
    project_files: dict[str, str]
    expected_test_name: str
    expected_sql_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CompileProgressIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_progress_prefixes: tuple[str, ...]


@dataclass(frozen=True)
class CteTypePropagationIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_column_name: str
    expected_column_type: str


@dataclass(frozen=True)
class DeferToIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    defer_to: str
    select: tuple[str, ...]
    expected_model_count: int
    expected_resolved_sql_fragments: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DiffSelectorIntegrationTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_model_names: frozenset[str]


@dataclass(frozen=True)
class AppendCursorPipelineIntegrationTestCase:
    description: str
    model_header_cursor_config: str
    expected_resolved_sql_fragment: str


@dataclass(frozen=True)
class SqlAnalysisChainCompileTargetIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    compiled_test_path: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]
    warehouse_setup_sql: tuple[str, ...] = ()


@dataclass(frozen=True)
class SnowflakeTargetValidationIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_error_fragment: str = ""
    expected_database: str | None = None
    expected_schema: str | None = None


@dataclass(frozen=True)
class ExpectedCountTestCase:
    description: str
    expected_count: int


@dataclass(frozen=True)
class SetOperationTypeIntegrationTestCase:
    description: str
    query_sql: str
    allowed_inferred_types: frozenset[str | None]
    expected_rows: tuple[tuple[float], ...]


@dataclass(frozen=True)
class SetOperationLineageIntegrationTestCase:
    description: str
    expected_sources: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class ReshapedStarIntegrationTestCase:
    """One PIVOT or UNPIVOT star query whose compiled columns must match DuckDB."""

    description: str
    query_sql: str
    expected_columns: tuple[str, ...]


@dataclass(frozen=True)
class ReshapedStarLineageIntegrationTestCase:
    """One PIVOT star query with the expected upstream columns of each output."""

    description: str
    query_sql: str
    expected_sources: tuple[frozenset[tuple[str, str]], ...]


@dataclass(frozen=True)
class SharedBindingQueryCase:
    description: str
    orders_summary_sql: str
    customers_summary_sql: str
    expected_shared_queries: int
    expected_codes: tuple[str, ...] = ()
    later_models: tuple[tuple[str, str], ...] = ()
    expected_lineage: tuple[tuple[str, str], ...] = ()
    expected_findings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class SingularAuditAttachmentIntegrationTestCase:
    description: str
    orders_header: str
    generic_audit_files: dict[str, str]
    expected_attachment: tuple[str, str | None]


@dataclass(frozen=True)
class PythonSourceReadPlanTestCase:
    description: str
    target_config: str
    expected_schema: str


@dataclass(frozen=True)
class FunctionArgumentTypeCase:
    description: str
    projection: str
    expected_codes: tuple[str, ...] = ()


type CompileOutcome = tuple[int, dict[str, object], dict[str, bytes]]
type PreparedCompile = tuple[
    CompileOutcome, tuple[str, ...], dict[str, object | None], tuple[bytes, ...]
]


@dataclass(frozen=True)
class DataflowOracleCase:
    description: str
    project: RandomDagProject
    reshaped_steps: tuple[tuple[int, ...], ...]
    expected_exit_codes: tuple[int, ...]
    compile_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataflowFixtureCase:
    description: str
    fixture: str
    expected_exit_code: int


@dataclass(frozen=True)
class DataflowDenseCase:
    description: str
    model_count: int
    expected_exit_codes: tuple[int, ...]


@dataclass(frozen=True)
class DataflowBuildCase:
    description: str
    project: RandomDagProject
    expected_compile_exit_code: int
    expected_build_exit_code: int


@dataclass(frozen=True)
class DataflowScheduleCase:
    description: str
    workers: int
    batch_limit: int
    max_delay_seconds: float
    expected_cold_exit_code: int = 1
    expected_edit_exit_code: int = 1


@dataclass(frozen=True)
class DataflowFailureCase:
    description: str
    failing_models: tuple[str, ...]
    expected_message: str


@dataclass(frozen=True)
class DataflowPoolCase:
    description: str
    compiles: int
    minimum_batches: int
    expected_pool_threads: int


@dataclass(frozen=True)
class DataflowInterruptCase:
    description: str
    expected_live_workers: tuple[str, ...]
    expected_overlaps: tuple[str, ...]
    expected_thread_errors: int
    expected_notices: int


@dataclass(frozen=True)
class DataflowInterruptAfterFaultCase:
    description: str
    failing_model: str
    interrupted_model: str
    expected_wave_replays: int


@dataclass(frozen=True)
class DataflowStartFailureCase:
    description: str
    failing_start: int
    interrupt_after_start: bool
    expected_error_type: type[BaseException]
    expected_error: str
    expected_live_workers: tuple[str, ...]
    expected_notices: int


@dataclass(frozen=True)
class BatchedPreparationCase:
    description: str
    write_project: Callable[[Path], tuple[str, ...]]
    reshaped: tuple[int, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class PerturbedPreparationCase:
    description: str
    project: RandomDagProject
    expected_payloads_match: bool
