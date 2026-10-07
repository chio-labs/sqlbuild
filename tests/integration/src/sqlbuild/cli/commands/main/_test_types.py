from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.planner.models import CursorOverrides


@dataclass(frozen=True)
class SemanticFixTestCase:
    description: str
    sql: str
    expected_code: str
    dialect: str = "duckdb"
    expected_status: str = "applied"


@dataclass(frozen=True)
class VariedCompileFixtureTestCase:
    description: str
    model_count: int
    expected_exit_code: int


@dataclass(frozen=True)
class PreparedArtifactsCompileTestCase:
    description: str
    model_count: int
    staging_directory_factory: Callable[[Path], None]
    expected_exit_code: int = 0


@dataclass(frozen=True)
class BackgroundTestPlanningCompileTestCase:
    description: str
    compile_args: tuple[str, ...]
    rules_config: str
    prepare_project: Callable[..., None]
    max_prepared_models: int = 5000
    expected_background_plans: tuple[str, ...] = ("sqlbuild-tests",)


@dataclass(frozen=True)
class BackgroundTestPlanningFailureTestCase:
    description: str
    compile_args: tuple[str, ...]
    test_options: str
    patch_native_planner: Callable[..., None]
    expected_error_fragment: str


@dataclass(frozen=True)
class AbandonedStagingCompileTestCase:
    description: str
    model_count: int
    abandoned: tuple[str, ...]
    locked: tuple[str, ...]
    expected_remaining: tuple[str, ...]


@dataclass(frozen=True)
class CrossDeviceArtifactsCompileTestCase:
    description: str
    model_count: int
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
class KeywordFunctionCompileTestCase:
    """Expected compile result for a DuckDB SQL keyword function projection."""

    description: str
    projection: str
    expected_exit_code: int
    expected_diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class StarExpansionCompileTestCase:
    """Expected diagnostics for a model reading a star over an inferred upstream."""

    description: str
    star_model_sql: str
    downstream_sql: str
    expected_exit_code: int
    expected_diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class StarLineageCompileTestCase:
    """Expected compile-report lineage for a star over a derived table."""

    description: str
    star_model_sql: str
    expected_edge_count: int


@dataclass(frozen=True)
class SnapshotValidityCompileTestCase:
    """Expected diagnostics for a model reading a snapshot relation."""

    description: str
    snapshot_config: str
    downstream_sql: str
    expected_exit_code: int
    expected_diagnostics: tuple[str, ...]


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
class CustomHostSplitIntegrationTestCase:
    """A compile whose custom rules run on several hosts and must match one host."""

    description: str
    model_count: int
    hosts: int
    expected_code: str


@dataclass(frozen=True)
class DollarQuotedLiteralBuildTestCase:
    """One model projection with dollar-quoted literals and its built rows."""

    description: str
    projection: str
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ImplicitAliasRuleIntegrationTestCase:
    """One model query and its expected unused-alias finding locations."""

    description: str
    query_sql: str
    expected_locations: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class NumericRangeDecisionIntegrationTestCase:
    """One numeric range or value-list predicate and its expected rule findings."""

    description: str
    predicate: str
    expected_findings: tuple[tuple[str, str], ...]
    expected_exit_code: int
    constants: str = ""


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
class AuthoredSpellingFormatIntegrationTestCase:
    """One authored function or operator spelling that formatting must keep."""

    description: str
    adapter: str
    authored_expression: str
    expected_expression: str


@dataclass(frozen=True)
class LayoutOnlyFormatIntegrationTestCase:
    """One adapter whose authored keywords, aliases and terminators formatting must keep."""

    description: str
    adapter: str
    expected_body: str


@dataclass(frozen=True)
class LineWidthWrapIntegrationTestCase:
    """One project line width and the wrapped model file formatting must produce."""

    description: str
    line_width: int
    authored_sql: str
    expected_sql: str


@dataclass(frozen=True)
class DollarQuoteFormatIntegrationTestCase:
    """One dollar-quoted literal whose quote state must not hide a later intrinsic call."""

    description: str
    literal: str
    expected_note: str


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
class FormatDescriptionFaultIntegrationTestCase:
    """A missing description faults format check and write mode alike."""

    description: str
    authored_sql: str
    expected_exit_code: int
    expected_code: str
    expected_severity: str
    expected_formatted_sql: str


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


@dataclass(frozen=True)
class SourceRebindingTestCase:
    """Expression-source inspection that must rebind downstream models only on new evidence."""

    description: str
    source_expression: str
    model_sql: str
    expected_exit_code: int
    expected_rebinding: bool
    expected_fragment: str = ""


@dataclass(frozen=True)
class DiscoveryWorkTestCase:
    """Commands that must discover a project with the same work as compile."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_eager_output_column_scans: int


@dataclass(frozen=True)
class NativeAllocatorEntryTestCase:
    description: str
    inherited_environment: tuple[tuple[str, str], ...]
    expected_purge_delay: str


@dataclass(frozen=True)
class UnusedOutputDifferentialCase:
    """One SQBRSQL042 CTE whose rows must survive `format --fix` unchanged."""

    description: str
    cte_sql: str
    reader_sql: str
    expected_statuses: tuple[str, ...]


@dataclass(frozen=True)
class WarmTargetTestCase:
    description: str
    compile_args: tuple[str, ...]
    expected_exit_code: int = 0
    expected_changed: tuple[str, ...] = ()
    expected_pruned: tuple[str, ...] = ("legacy", "empty")
    expected_link_kept: bool = True


@dataclass(frozen=True)
class WarmTargetEditTestCase:
    description: str
    edited_path: str
    edited_contents: str
    expected_changed: tuple[str, ...]
    expected_exit_code: int = 0


@dataclass(frozen=True)
class RuleExceptionPolicyTestCase:
    """One `[rules] allow_exceptions` value with one escape hatch, compiled through the CLI."""

    description: str
    rules_toml: str
    directive: str
    expected_exit_code: int
    expected_fragments: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormatExceptionPolicyTestCase:
    """One `[rules] allow_exceptions` value read by `sqb format`."""

    description: str
    setting: str
    expected_exit_code: int
    expected_fragment: str
    expected_compile_fragment: str


@dataclass(frozen=True)
class RepeatedJsonParseTestCase:
    """One model body checked by SQBRSQL045 through the CLI."""

    description: str
    adapter: str
    header: str
    sql: str
    expected_locations: tuple[tuple[int, int], ...]
    expected_detail: str = ""
    extra_files: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CommandWarehouseCliTestCase:
    """One real CLI invocation and the only warehouse its Snowflake sessions may use."""

    description: str
    argv: tuple[str, ...]
    expected_warehouse: str
    warehouses_section: str = '[targets.dev.warehouses]\nbuild = "BUILD_WH"\nquery = "ADHOC_WH"\n'
    local_config: str = ""


@dataclass(frozen=True)
class CommandWarehouseOutputTestCase:
    """One real CLI invocation and the warehouse report it must print."""

    description: str
    argv: tuple[str, ...]
    expected_fragments: tuple[str, ...]
    warehouses_section: str = '[targets.dev.warehouses]\nbuild = "BUILD_WH"\nquery = "ADHOC_WH"\n'
    local_config: str = ""


@dataclass(frozen=True)
class CommandWarehouseDebugJsonTestCase:
    """One `sqb debug --json` invocation and the warehouse lines it must report."""

    description: str
    argv: tuple[str, ...]
    expected_lines: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class CommandWarehouseExitTestCase:
    """One real CLI invocation, its exit code, and the output it must print."""

    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_fragments: tuple[str, ...]
    expected_connect_calls: int = 0
    warehouses_section: str = '[targets.dev.warehouses]\nbuild = "BUILD_WH"\nquery = "ADHOC_WH"\n'
    local_config: str = ""


@dataclass(frozen=True)
class StartupImportFootprintTestCase:
    """One fresh-process CLI invocation and the heavy modules it must not load."""

    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    forbidden_modules: tuple[str, ...]


@dataclass(frozen=True)
class ReusedCompileImportFootprintTestCase:
    """One reused compile in a fresh process and the compile modules it must not load."""

    description: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_reuse_message: str
    forbidden_modules: tuple[str, ...]


@dataclass(frozen=True)
class DefaultConnectionCliTestCase:
    """One CLI command against a project whose target does not set connection."""

    description: str
    project_toml: str
    argv: tuple[str, ...]
    expected_exit_code: int
    expected_output_fragments: tuple[str, ...]
    expected_order_rows: tuple[tuple[object, ...], ...] | None = None


@dataclass(frozen=True)
class InferredFreshnessCliTestCase:
    """One source whose freshness strategy and type come from its declaration."""

    description: str
    sources_yaml: str
    expected_sources: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class FixSessionTestCase:
    """A Rule fix under an engine whose discovery retains a native session."""

    description: str
    engine: str
    expected_original_sessions: tuple[bool, ...]
    expected_fix_pass_sessions: frozenset[bool]
