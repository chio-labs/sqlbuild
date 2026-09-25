from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from tempfile import TemporaryDirectory

from sqlbuild.compiler.planner.models import CursorOverrides


@dataclass(frozen=True)
class VariedCompileFixtureTestCase:
    description: str
    model_count: int
    expected_exit_code: int


@dataclass(frozen=True)
class PreparedArtifactsCompileTestCase:
    description: str
    model_count: int
    temporary_directory_factory: Callable[..., TemporaryDirectory[str]]
    expected_exit_code: int = 0


@dataclass(frozen=True)
class BoundProjectionCompileTestCase:
    description: str
    query_sql: str
    expected_rows: tuple[tuple[int | None, ...], ...]
    expected_edges: int
    output_contract: str = "order_id (type BIGINT, nullable false)"


@dataclass(frozen=True)
class AliasSourceCompileTestCase:
    """Lexical source shape exercised by an input-column precedence regression."""

    description: str
    query_prefix: str
    source_relation: str
    expected_edge_count: int


@dataclass(frozen=True)
class DerivedNativeCompileTestCase:
    """Expected compiled and executed output from the native query graph."""

    description: str
    query_sql: str
    expected_exit_code: int
    expected_diagnostics: tuple[str, ...]
    expected_rows: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class CombinedCompilationTestCase:
    """Expected CLI behavior for schema-bound CTE compilation."""

    description: str
    projection: str
    expected_exit_code: int
    expected_diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class RulesIntegrationTestCase:
    """One compiler-integrated Rules command expectation."""

    description: str
    expected_exit_code: int
    expected_code: str


@dataclass(frozen=True)
class RulePassIntegrationTestCase:
    """One compiler-integrated Rules command expected to pass."""

    description: str
    expected_exit_code: int
    expected_diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class ExplicitContractOutputRuleIntegrationTestCase:
    """One explicit contract output Rule expectation through compile."""

    description: str
    query_sql: str
    expected_exit_code: int
    expected_rule_findings: int
    columns_sql: str = "order_id (type INTEGER)"


@dataclass(frozen=True)
class TypedContractRuleIntegrationTestCase:
    """One fully typed contract Rule expectation through compile."""

    description: str
    columns_sql: str
    expected_exit_code: int
    expected_contract_101_findings: int
    expected_contract_105_findings: int
    expected_contract_106_findings: int


@dataclass(frozen=True)
class DynamicPivotRulesIntegrationTestCase:
    description: str
    expected_valid_exit_code: int
    expected_invalid_exit_code: int
    expected_invalid_model_findings: int
    expected_invalid_sql_findings: int


@dataclass(frozen=True)
class SnowflakeCompileIntegrationTestCase:
    """One Snowflake SQL compatibility expectation through compile."""

    description: str
    query_sql: str
    expected_exit_code: int
    expected_diagnostics: tuple[str, ...]
    expected_query_fragment: str


@dataclass(frozen=True)
class ContractNullabilityCompileIntegrationTestCase:
    """One contract nullability expectation through compile."""

    description: str
    column_sql: str
    expected_exit_code: int
    expected_diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class ProjectDirectoryCompileIntegrationTestCase:
    """One project-directory normalization expectation through compile."""

    description: str
    expected_exit_code: int


@dataclass(frozen=True)
class FormatCompileIntegrationTestCase:
    """One format-to-compile compatibility expectation."""

    description: str
    expected_literal: str


@dataclass(frozen=True)
class BacktickDialectFormatIntegrationTestCase:
    """One backtick-identifier adapter whose macro call must survive formatting."""

    description: str
    adapter: str
    expected_literal: str


@dataclass(frozen=True)
class DescriptionFormatIntegrationTestCase:
    """One description wrapping expectation through the real CLI and compiler."""

    description: str
    line_width: int
    authored_description: str
    expected_formatted_description: str


@dataclass(frozen=True)
class FormatSafetyIntegrationTestCase:
    """One format safety expectation through the real CLI."""

    description: str
    authored_sql: str
    expected_fault_code: str
    expected_exit_code: int


@dataclass(frozen=True)
class FormatterDeclineIntegrationTestCase:
    """One expected native formatter decline through the real CLI."""

    description: str
    authored_body: str
    expected_exit_code: int


@dataclass(frozen=True)
class TypedNullFormatIntegrationTestCase:
    """One single-pass typed-null fixture formatting expectation."""

    description: str
    fixture_projection: str
    expected_literal: str
    expected_exit_code: int


@dataclass(frozen=True)
class CanonicalFixtureFormatIntegrationTestCase:
    """One post-native fixture simplification expectation."""

    description: str
    expected_retained_literal: str
    expected_removed_literal: str
    expected_exit_code: int


@dataclass(frozen=True)
class FromValuesFormatIntegrationTestCase:
    """One dialect expectation for an unparenthesized values relation."""

    description: str
    adapter: str
    expected_exit_code: int
    expected_literal: str


@dataclass(frozen=True)
class MixedFromValuesFormatIntegrationTestCase:
    """One positional values-relation preservation expectation."""

    description: str
    authored_query: str
    expected_parenthesized_literal: str
    expected_unparenthesized_literal: str
    expected_exit_code: int


@dataclass(frozen=True)
class FormatScopeIntegrationTestCase:
    """Expected CLI outcomes for the format selection contract."""

    description: str
    expected_exclude_exit: int
    expected_selected_model_exit: int
    expected_path_with_exclude_exit: int
    expected_exclude_path_exit: int


@dataclass(frozen=True)
class FormatWarningIntegrationTestCase:
    """One non-failing format warning expectation."""

    description: str
    expected_exit_code: int
    expected_code: str
    expected_severity: str


@dataclass(frozen=True)
class ContractCommandIntegrationTestCase:
    """One target-backed contract CLI expectation."""

    description: str
    expected_exit_code: int


@dataclass(frozen=True)
class LoadCommandIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragment: str
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_stdout_absent_fragments: tuple[str, ...] = ()
    expected_json_staging_relation: str | None = None
    expected_json_rows_loaded: int = 0
    expected_lifecycle_sql_fragments: tuple[str, ...] = ()
    select: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None


@dataclass(frozen=True)
class LoadCommandSelectionErrorTestCase:
    description: str
    project_files: dict[str, str]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class LoadCommandEmptySelectionTestCase:
    description: str
    project_files: dict[str, str]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragment: str
    expected_stdout_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandConcurrencyTestCase:
    description: str
    project_files: dict[str, str]
    max_concurrency: int
    expected_connection_count: int
    expected_source_order: tuple[str, ...]
    expected_json_asset_order: tuple[str, ...]


@dataclass(frozen=True)
class LoadCommandInferredColumnsTestCase:
    description: str
    project_files: dict[str, str]
    expected_row: tuple[object, ...]
    expected_column_types: dict[str, str]


@dataclass(frozen=True)
class LoadCommandMultipleYieldTestCase:
    description: str
    project_files: dict[str, str]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class LoadCommandBatchedYieldTestCase:
    description: str
    project_files: dict[str, str]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_column_types: dict[str, str]
    expected_lifecycle_sql_fragments: tuple[str, ...]


@dataclass(frozen=True)
class LoadCommandBatchedRowsTestCase:
    description: str
    project_files: dict[str, str]
    select_sql: str
    table_name: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_column_types: dict[str, str]
    expected_rows_loaded: int
    expected_lifecycle_sql_fragments: tuple[str, ...] = ()
    absent_lifecycle_sql_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandLifecycleOrderTestCase:
    description: str
    project_files: dict[str, str]
    expected_lifecycle_sql_order: tuple[str, ...]


@dataclass(frozen=True)
class LoadCommandWriteStrategyTestCase:
    description: str
    project_files: dict[str, str]
    select_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    run_count: int = 2


@dataclass(frozen=True)
class LoadCommandWriteStrategyLifecycleTestCase:
    description: str
    project_files: dict[str, str]
    expected_first_run_fragments: tuple[str, ...]
    expected_second_run_fragments: tuple[str, ...]
    absent_second_run_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandCursorNoneTestCase:
    description: str
    project_files: dict[str, str]
    select_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    run_count: int = 2
    setup_sql: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandLifecycleSqlTestCase:
    description: str
    project_files: dict[str, str]
    run_count: int
    expected_lifecycle_sql_fragments: tuple[str, ...] = ()
    absent_lifecycle_sql_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoadCommandAdapterCallTestCase:
    description: str
    project_files: dict[str, str]
    method_name: str
    expected_sql: str
    expected_arguments: tuple[str | None, ...] = ()


@dataclass(frozen=True)
class LoadCommandReloadContextTestCase:
    description: str
    project_files: dict[str, str]
    reload: bool
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class LoadCommandCursorOverrideContextTestCase:
    description: str
    project_files: dict[str, str]
    cursor_overrides: CursorOverrides | None
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class LoadCommandEmptyRowsTestCase:
    description: str
    project_files: dict[str, str]
    expected_column_types: dict[str, str]


@dataclass(frozen=True)
class LoadCommandFailureTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_stdout_fragment: str


@dataclass(frozen=True)
class LoadCommandFailureCleanupTestCase:
    description: str
    project_files: dict[str, str]
    staging_table_name: str
    expected_staging_exists: bool
    setup_sql: tuple[str, ...] = ()
    target_select_sql: str = "SELECT NULL WHERE FALSE"
    expected_target_rows: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True)
class BuildRunAutoLoadTestCase:
    description: str
    command: str
    expected_stdout_fragments: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SourceDeferralBuildTestCase:
    description: str
    command: str
    project_files: dict[str, str]
    defer_sources_to: str | None
    setup_sql: tuple[str, ...]
    expected_model_rows: tuple[tuple[object, ...], ...]
    expected_loaded_source_rows: tuple[tuple[object, ...], ...]
    expected_exit_code: int = 0


@dataclass(frozen=True)
class ManagedSourcePlanningErrorTestCase:
    description: str
    project_files: dict[str, str]
    expected_error_fragment: str
    defer_sources_to: str | None = None
    select: tuple[str, ...] = ("stg_orders",)


@dataclass(frozen=True)
class SourceDeferralNoErrorTestCase:
    description: str
    project_files: dict[str, str]
    setup_sql: tuple[str, ...]
    select: tuple[str, ...]
    result_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    expected_exit_code: int = 0
    defer_sources_to: str | None = None
    command: str = "build"
    load_sources: bool | None = None
    command_options: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceDeferralArtifactTestCase:
    description: str
    command: str
    project_files: dict[str, str]
    setup_sql: tuple[str, ...]
    select: tuple[str, ...]
    compiled_relative_paths: tuple[str, ...]
    runtime_relative_paths: tuple[str, ...]
    expected_sql_fragments: tuple[str, ...]
    unexpected_sql_fragments: tuple[str, ...] = ()
    defer_sources_to: str | None = None


@dataclass(frozen=True)
class BuildRunAutoLoadFlagTestCase:
    description: str
    command: str
    project_files: dict[str, str]
    args: tuple[str, ...]
    setup_sql: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_stdout_absent_fragments: tuple[str, ...] = ()
    load_sources: bool | None = None


@dataclass(frozen=True)
class BuildRunAutoLoadSelectionTestCase:
    description: str
    args: tuple[str, ...]
    setup_sql: tuple[str, ...]
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...] = ()
    expected_stdout_absent_fragments: tuple[str, ...] = ()
    project_files: dict[str, str] | None = None
    result_table: str = "fact_orders"


@dataclass(frozen=True)
class BuildRunAutoLoadFailureTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_model_exists: bool


@dataclass(frozen=True)
class BuildRunAutoLoadJsonTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_source_asset: dict[str, object]


@dataclass(frozen=True)
class PlanAutoLoadOutputTestCase:
    description: str
    project_files: dict[str, str]
    load_sources: bool | None
    expected_stdout_fragments: tuple[str, ...]
    expected_stdout_absent_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanAutoLoadJsonTestCase:
    description: str
    project_files: dict[str, str]
    load_sources: bool | None
    expected_source_loads: tuple[dict[str, object], ...]
    expected_selected_count: int
    expected_source_load_count: int


@dataclass(frozen=True)
class ExpectedBooleanTestCase:
    description: str
    expected_result: bool


@dataclass(frozen=True)
class ExpectedCountTestCase:
    description: str
    expected_count: int


@dataclass(frozen=True)
class ExpectedMessageTestCase:
    description: str
    expected_message: str


@dataclass(frozen=True)
class DenseCompileFixtureTestCase:
    description: str
    model_count: int
    expected_rule_misses: int
    expected_tail_lineage_edges: int


@dataclass(frozen=True)
class TargetRetentionViewsTestCase:
    description: str
    view_header: str
    expected_exit_code: int
    expected_fragment: str


@dataclass(frozen=True)
class RetentionDecreasePolicyTestCase:
    description: str
    target_lines: tuple[str, ...]
    build_flags: tuple[str, ...]
    expected_exit_code: int
    expected_fragment: str


@dataclass(frozen=True)
class TargetMaterializationRetentionTestCase:
    description: str
    target_lines: tuple[str, ...]
    expected_requested_days: frozenset[int]


@dataclass(frozen=True)
class BuildTestPlanningTestCase:
    description: str
    build_flags: tuple[str, ...]
    expected_exit_code: int
    expected_fragment: str


@dataclass(frozen=True)
class FormatPathArgumentsIntegrationTestCase:
    """One `sqb format` invocation that names files directly."""

    description: str
    arguments: tuple[str, ...]
    expected_exit_code: int
    expected_formatted: tuple[str, ...]
    expected_unchanged: tuple[str, ...]
    expected_output_fragment: str


@dataclass(frozen=True)
class LeadingCteCommentFormatIntegrationTestCase:
    """One leading CTE comment that must survive formatting and compile."""

    description: str
    authored_sql: str
    expected_fragment: str


@dataclass(frozen=True)
class DroppedRelationRecoveryTestCase:
    """One model whose relation is dropped outside SQLBuild after a successful build."""

    description: str
    model_sql: str
    drop_sql: str
    expected_action: str
    expected_rows: tuple[tuple[object, ...], ...]
    settings_toml: str = ""
    stale_artifact_sql: str = "SELECT 1"


@dataclass(frozen=True)
class DroppedIncrementalFirstRunRangeTestCase:
    """One incremental model rebuilt from its configured start after an external drop."""

    description: str
    model_sql: str
    expected_start: str
    expected_end: str
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DroppedSeedPlanTestCase:
    """One seed dropped outside SQLBuild after a successful build."""

    description: str
    model_sql: str
    expected_steady_reasons: dict[str, object]
    expected_dropped_reasons: dict[str, object]
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class AbsentMicrobatchFullRefreshTestCase:
    """One full-refresh build of a microbatch model whose live target is absent."""

    description: str
    batch_concurrency: int
    setup_build_flags: tuple[str, ...]
    setup_drop_sql: str
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SqlReadabilityTestCase:
    """One authored SQL readability contract case."""

    description: str
    sql: str
    expected_fault: bool
    rule_code: str = "SQBRSQL041"


@dataclass(frozen=True)
class FormatterSyntaxTestCase:
    """Authored constructs that must survive canonical layout formatting."""

    description: str
    sql: str
    expected_fragments: tuple[str, ...]
    macro_source: str = ""


@dataclass(frozen=True)
class UnicodeRuleLocationTestCase:
    """SQL rule diagnostics expressed in authored Unicode character coordinates."""

    description: str
    rule_code: str
    sql: str
    expected_anchors: tuple[str, ...]
