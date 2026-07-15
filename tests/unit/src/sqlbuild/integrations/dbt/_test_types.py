from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtInteropParsedArgs,
    DbtLsNode,
    DbtManifestIndex,
)
from sqlbuild.integrations.dbt.types import (
    DbtLineageDirection,
    DbtLineageOutputFormat,
    DbtModelOutcomeState,
    DbtModelPlanAction,
    DbtModelPlanReason,
)
from sqlbuild.spec.contracts.models import DbtConfig, LocalDbtConfig


@dataclass(frozen=True)
class DbtConfigResolutionTestCase:
    description: str
    config: DbtConfig
    cli_project_dir: str | None
    cli_profiles_dir: str | None
    cli_target: str | None
    cli_target_path: str | None
    require_project_dir: bool
    expected_project_dir: Path | None
    expected_profiles_dir: Path | None
    expected_target: str | None
    expected_target_path: Path | None
    local_config: LocalDbtConfig = field(default_factory=LocalDbtConfig)


@dataclass(frozen=True)
class DbtConfigErrorTestCase:
    description: str
    config: DbtConfig
    cli_project_dir: str | None
    expected_error_fragment: str
    expected_code: str
    expected_help_fragment: str


@dataclass(frozen=True)
class DbtVarsResolutionTestCase:
    description: str
    project_config: DbtConfig
    local_config: LocalDbtConfig
    dbt_args: tuple[str, ...]
    expected_vars: dict[str, object]


@dataclass(frozen=True)
class DbtArgvTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    resource_types: tuple[str, ...]
    expected_argv: tuple[str, ...]


@dataclass(frozen=True)
class DbtLsParseTestCase:
    description: str
    stdout: str
    expected_unique_ids: tuple[str, ...]
    expected_resource_types: tuple[str | None, ...]
    expected_selector_terms: tuple[str, ...]


@dataclass(frozen=True)
class DbtRunnerMemoTestCase:
    description: str
    command_result: DbtCommandResult
    expected_call_count: int


@dataclass(frozen=True)
class DbtRunnerCommandTestCase:
    description: str
    command_result: DbtCommandResult
    expected_argv: tuple[str, ...]


@dataclass(frozen=True)
class DbtReuseGitTimeoutTestCase:
    description: str
    timeout_seconds: int
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtReuseGitRefreshTestCase:
    description: str
    git_ref: str
    refresh: bool
    expected_archive_ref: str
    expected_run_calls: int


@dataclass(frozen=True)
class DbtReuseCompileDepsTestCase:
    description: str
    expected_commands: tuple[str, ...]
    expected_manifest_contents: str


@dataclass(frozen=True)
class DbtReuseManifestCacheTestCase:
    description: str
    expected_first_commands: tuple[str, ...]
    expected_second_commands: tuple[str, ...]
    expected_manifest_contents: str


@dataclass(frozen=True)
class DbtModeGuardTestCase:
    description: str
    virtual_environments: bool
    expected_error_fragment: str | None
    expected_code: str | None
    expected_help_fragment: str | None


@dataclass(frozen=True)
class DbtSelectionErrorTestCase:
    description: str
    manifest_data: dict[str, object]
    sqlbuild_model_sql_by_name: dict[str, str]
    sqlbuild_model_tags_by_name: dict[str, tuple[str, ...]]
    sqlbuild_model_path_by_name: dict[str, str]
    select: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtExecutionSpacingTestCase:
    description: str
    expected_spacing_fragment: str
    expected_no_work_spacing_fragment: str
    unexpected_no_blank_fragment: str
    unexpected_no_work_no_blank_fragment: str
    unexpected_extra_blank_fragment: str
    unexpected_no_work_extra_blank_fragment: str


@dataclass(frozen=True)
class DbtCompileFullRefreshPipelineTestCase:
    description: str
    command: str
    expected_full_refresh_values: tuple[bool, ...]


@dataclass(frozen=True)
class DbtDeferCloneResolutionTestCase:
    description: str
    cli_defer_clone_from: bool | None
    project_defer_clone_from: bool
    local_defer_clone_from: bool | None
    expected_defer_clone_from: bool


@dataclass(frozen=True)
class DbtEventParseTestCase:
    description: str
    event: dict[str, object]
    expected_unique_id: str
    expected_resource_type: str
    expected_node_name: str
    expected_status: str
    expected_message_count: int = 0
    expected_database: str | None = None
    expected_schema: str | None = None
    expected_node_checksum: str | None = None
    expected_total: int | None = None


@dataclass(frozen=True)
class DbtEventStreamTestCase:
    description: str
    stdout_lines: tuple[str, ...]
    expected_unique_ids: tuple[str, ...]
    expected_output_fragments: tuple[str, ...] = ()
    expected_rendered_rows: int | None = None


@dataclass(frozen=True)
class DbtSilentStatusRefreshTestCase:
    description: str
    silent_seconds: float
    refresh_seconds: float
    expected_initial_status: str
    expected_refreshed_status: str


@dataclass(frozen=True)
class DbtDebugPipelineTestCase:
    description: str
    args: tuple[str, ...]
    expected_argv: tuple[str, ...]
    expected_stdout: str
    expected_stderr: str
    expected_returncode: int


@dataclass(frozen=True)
class DbtManifestResolutionTestCase:
    description: str
    manifest_data: dict[str, object]
    package_name: str | None
    model_name: str
    expected_relation_name: str


@dataclass(frozen=True)
class DbtManifestResolutionErrorTestCase:
    description: str
    manifest_data: dict[str, object]
    package_name: str | None
    model_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtManifestSourceIndexTestCase:
    description: str
    manifest_data: dict[str, object]
    expected_unique_id: str
    expected_source_name: str
    expected_name: str
    expected_relation_name: str


@dataclass(frozen=True)
class DbtManifestIndexErrorTestCase:
    description: str
    manifest_data: dict[str, object]
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtSourceFreshnessTranslationTestCase:
    description: str
    manifest_data: dict[str, object]
    expected_source_name: str
    expected_strategy: str | None
    expected_column: str | None = None
    expected_query: str | None = None
    expected_filter: str | None = None
    expected_warn_after: str | None = None
    expected_error_after: str | None = None
    expected_table: str | None = None
    expected_source_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtSourceFreshnessTranslationErrorTestCase:
    description: str
    manifest_data: dict[str, object]
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtModelPlanningTestCase:
    description: str
    create_relation: bool
    fingerprint_hash: str | None
    expected_action: DbtModelPlanAction
    expected_reason: DbtModelPlanReason
    force: bool = False


@dataclass(frozen=True)
class DbtModelPlanningRelationPrefetchTestCase:
    description: str
    expected_list_relation_call_count: int
    expected_relation_exists_call_count: int
    expected_reasons_by_unique_id: dict[str, DbtModelPlanReason]


@dataclass(frozen=True)
class DbtSeedRelationPrefetchTestCase:
    description: str
    seed_names: tuple[str, ...]
    existing_seed_names: tuple[str, ...]
    expected_changed_seed_names: tuple[str, ...]
    expected_seed_relation_exists_call_count: int


@dataclass(frozen=True)
class DbtExecutionSelectionStatusTestCase:
    description: str
    expected_total: int
    expected_output_fragment: str
    expected_completion_fragment: str


@dataclass(frozen=True)
class DbtFingerprintWriteTestCase:
    description: str
    query_sql: str
    node_checksum: str
    expected_definition: str
    expected_version_hash: str
    expected_metadata_fragment: str


@dataclass(frozen=True)
class DbtModelSourceBlockingTestCase:
    description: str
    expected_blocked_unique_ids: tuple[str, ...]
    expected_blocked_sqlbuild_model_names: tuple[str, ...]
    expected_blocked_source_unique_ids: tuple[str, ...]


@dataclass(frozen=True)
class DbtSourceFreshnessScopeTestCase:
    description: str
    candidate_unique_ids: tuple[str, ...]
    expected_freshness_request_names: tuple[str, ...]


@dataclass(frozen=True)
class DbtExecutionArgvPruningTestCase:
    description: str
    expected_argv: tuple[str, ...] | None


@dataclass(frozen=True)
class DbtExecutionOutcomeTestCase:
    description: str
    expected_states_by_unique_id: tuple[tuple[str, DbtModelOutcomeState], ...]
    expected_stale_sqlbuild_model_names: tuple[str, ...]
    expected_blocked_sqlbuild_model_names: tuple[str, ...]
    expected_output_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtRunResultsFallbackRenderTestCase:
    description: str
    unique_id: str
    status: str
    message: str
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtExecutionTotalRenderTestCase:
    description: str
    expected_output_fragments: tuple[str, ...]
    unexpected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtExecutionSummaryFooterTestCase:
    description: str
    node_statuses: tuple[str, ...]
    expected_footer: str | None


@dataclass(frozen=True)
class DbtCombinedGraphTestCase:
    description: str
    manifest_data: dict[str, object]
    sqlbuild_model_sql_by_name: dict[str, str]
    expected_upstream_edges: tuple[tuple[str, tuple[str, ...]], ...]
    expected_downstream_from: str
    expected_downstream_keys: tuple[str, ...]
    expected_upstream_from: str
    expected_upstream_keys: tuple[str, ...]


@dataclass(frozen=True)
class DbtLineageSelectionTestCase:
    description: str
    target: str
    direction: DbtLineageDirection
    depth: int | None
    expected_node_ids: tuple[str, ...]
    expected_edges: tuple[tuple[str, str], ...]
    expected_focus_ids: tuple[str, ...]


@dataclass(frozen=True)
class DbtLineageSelectionErrorTestCase:
    description: str
    target: str
    expected_error_fragment: str
    expected_code: str


@dataclass(frozen=True)
class DbtLineageArgsTestCase:
    description: str
    args: tuple[str, ...]
    expected_target: str
    expected_output_format: DbtLineageOutputFormat
    expected_direction: DbtLineageDirection
    expected_depth: int | None
    expected_no_sql_validation: bool
    expected_dbt_args: tuple[str, ...]


@dataclass(frozen=True)
class DbtLineageArgsErrorTestCase:
    description: str
    args: tuple[str, ...]
    expected_error_fragment: str
    expected_code: str


@dataclass(frozen=True)
class DbtLineageOutputTestCase:
    description: str
    formatter: Callable[..., str]
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtLineageJsonOutputTestCase:
    description: str
    expected_node_metadata: tuple[tuple[str, str, object], ...]
    expected_direction: str


@dataclass(frozen=True)
class DbtColumnLineageSelectionTestCase:
    description: str
    target: str
    direction: DbtLineageDirection
    expected_edges: tuple[tuple[str, str], ...]
    expected_warnings: tuple[str, ...] = ()
    depth: int | None = None
    expected_target: tuple[str, str, str] | None = None
    expected_truncated: bool = False
    expected_transforms: tuple[str, ...] = ()
    expected_confidences: tuple[str, ...] = ()
    expected_is_column_target: bool = True


@dataclass(frozen=True)
class DbtSourceSchemaInspectionTestCase:
    description: str
    adapter_factory: Callable[[], BaseAdapter]
    expected_columns: tuple[str, ...]
    expected_warnings: tuple[str, ...]


@dataclass(frozen=True)
class DbtColumnLineageErrorTestCase:
    description: str
    target: str
    direction: DbtLineageDirection
    expected_error_fragment: str
    expected_code: str


@dataclass(frozen=True)
class DbtColumnLineageOutputTestCase:
    description: str
    output_format: DbtLineageOutputFormat
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtArgRoutingTestCase:
    description: str
    command: str
    parsed: DbtInteropParsedArgs
    expected_select: tuple[str, ...]
    expected_exclude: tuple[str, ...]
    expected_dbt_args: tuple[str, ...]
    expected_sqlbuild_args: tuple[str, ...]
    expected_defer_clone_from: bool | None = None


@dataclass(frozen=True)
class DbtArgRoutingErrorTestCase:
    description: str
    command: str
    parsed: DbtInteropParsedArgs
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtArgParseTestCase:
    description: str
    command: str
    args: tuple[str, ...]
    expected_select: tuple[str, ...]
    expected_exclude: tuple[str, ...]
    expected_full_refresh: bool
    expected_target: str | None
    expected_dbt_passthrough: tuple[str, ...]
    expected_defer_clone_from: bool | None = None


@dataclass(frozen=True)
class DbtArgParseErrorTestCase:
    description: str
    command: str
    args: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtSelectionTestCase:
    description: str
    manifest_data: dict[str, object]
    sqlbuild_model_sql_by_name: dict[str, str]
    sqlbuild_model_tags_by_name: dict[str, tuple[str, ...]]
    sqlbuild_model_path_by_name: dict[str, str]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    dbt_anchor_unique_ids_by_term: dict[str, tuple[str, ...]]
    expected_sqlbuild_model_names: tuple[str, ...]
    expected_dbt_required_unique_ids: tuple[str, ...]
    expected_dbt_anchor_terms: tuple[str, ...] = ()
    expected_dbt_anchor_unique_ids_by_term: dict[str, tuple[str, ...]] | None = None
    expected_path_translations: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DbtDeferCloneViewChainTermsTestCase:
    description: str
    manifest_data: dict[str, object]
    sqlbuild_model_sql_by_name: dict[str, str]
    selected_sqlbuild_model_names: tuple[str, ...]
    selected_dbt_unique_ids: tuple[str, ...]
    expected_terms: tuple[str, ...]
    expected_unique_ids: frozenset[str]
    expected_clone_unique_ids: frozenset[str]


@dataclass(frozen=True)
class DbtPlanTestCase:
    description: str
    command: str
    dbt_command_argv: tuple[str, ...]
    dbt_ls_unique_ids: tuple[str, ...]
    sqlbuild_command_argvs: tuple[tuple[str, ...], ...]
    selection_sqlbuild_model_names: tuple[str, ...]
    selection_dbt_required_unique_ids: tuple[str, ...]
    selection_dbt_anchor_terms: tuple[str, ...]
    selection_dbt_anchor_unique_ids_by_term: dict[str, tuple[str, ...]]
    selection_path_translations: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]
    expected_dbt_skipped: bool
    expected_sqlbuild_skipped: bool
    expected_human_fragments: tuple[str, ...]
    expected_json_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DbtPlanHumanFormatterTestCase:
    description: str
    dbt_ls_nodes: tuple[DbtLsNode, ...]
    sqlbuild_model_names: tuple[str, ...]
    sqlbuild_plan_model_names: tuple[str, ...]
    display_limit: int | None
    use_color: bool
    expected_human_fragments: tuple[str, ...]
    expected_human_regex_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]
    sqlbuild_command_argvs: tuple[tuple[str, ...], ...] = ()
    sqlbuild_plan_output: PlanOutput | None = None


@dataclass(frozen=True)
class DbtPlanOrchestrationTestCase:
    description: str
    command: str
    manifest_data: dict[str, object]
    sqlbuild_model_sql_by_name: dict[str, str]
    sqlbuild_model_tags_by_name: dict[str, tuple[str, ...]]
    sqlbuild_model_path_by_name: dict[str, str]
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    full_dbt_ls_unique_ids: tuple[str, ...]
    anchor_dbt_ls_unique_ids_by_term: dict[str, tuple[str, ...]]
    expected_dbt_ls_selects: tuple[tuple[str, ...], ...]
    expected_sqlbuild_model_names: tuple[str, ...]
    expected_dbt_required_unique_ids: tuple[str, ...]
    expected_dbt_required_selector_terms: tuple[str, ...]
    expected_supplemental_dbt_command_argvs: tuple[tuple[str, ...], ...]
    expected_sqlbuild_command_argvs: tuple[tuple[str, ...], ...]
    expected_dbt_skipped: bool
    expected_sqlbuild_skipped: bool
    dbt_options: DbtCliOptions | None = None
    dbt_command_args: tuple[str, ...] = ()
    sqlbuild_command_args: tuple[str, ...] = ()
    expected_primary_dbt_command_argv: tuple[str, ...] = ()
    expected_dbt_ls_excludes: tuple[tuple[str, ...], ...] = ()
    expected_dbt_anchor_terms: tuple[str, ...] = ()
    expected_path_translations: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtPlanOrchestrationErrorTestCase:
    description: str
    select: tuple[str, ...]
    failed_select: tuple[str, ...]
    expected_error_fragment: str
    expected_code: str
    expected_help_fragment: str


@dataclass(frozen=True)
class DbtDiffOptionsTestCase:
    description: str
    args: tuple[str, ...]
    expected_select: tuple[str, ...]
    expected_exclude: tuple[str, ...]
    expected_full: bool
    expected_schema_only: bool
    expected_bounded: str | None
    expected_verbose: bool
    expected_max_column_examples: int
    expected_max_row_only_examples: int
    expected_dbt_args: tuple[str, ...]


@dataclass(frozen=True)
class DbtCloneOptionsTestCase:
    description: str
    args: tuple[str, ...]
    expected_select: tuple[str, ...]
    expected_exclude: tuple[str, ...]
    expected_hard_copy: bool
    expected_no_sql_validation: bool
    expected_dbt_args: tuple[str, ...]


@dataclass(frozen=True)
class DbtCloneOptionsErrorTestCase:
    description: str
    args: tuple[str, ...]
    expected_error_fragment: str
    expected_help_fragment: str


@dataclass(frozen=True)
class DbtCloneExecuteTestCase:
    description: str
    current_materialized: str
    reuse_materialized: str
    create_destination_relation: bool
    create_origin_relation: bool
    include_reuse_manifest_model: bool
    expected_item_count: int
    expected_action: str | None
    expected_status: str | None
    expected_destination_rows: tuple[tuple[object, ...], ...]
    selected_resource_type: str = "model"


@dataclass(frozen=True)
class DbtCloneExecutionOrderTestCase:
    description: str
    expected_item_names: tuple[str, ...]
    expected_child_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class DbtDiffOptionsErrorTestCase:
    description: str
    args: tuple[str, ...]
    expected_error_fragment: str
    expected_code: str


@dataclass(frozen=True)
class DbtDiffUniqueKeyTestCase:
    description: str
    config: dict[str, object]
    expected_unique_key: tuple[str, ...]


@dataclass(frozen=True)
class DbtDiffUniqueKeyErrorTestCase:
    description: str
    config: dict[str, object]
    expected_error_fragment: str
    expected_code: str


@dataclass(frozen=True)
class DbtDiffBoundedCursorTestCase:
    description: str
    node_meta: dict[str, object] | None
    config_meta: dict[str, object] | None
    bounded: str
    expected_cursor_column: str
    expected_cursor_kind: str
    expected_has_end_cursor: bool


@dataclass(frozen=True)
class DbtDiffBoundedCursorErrorTestCase:
    description: str
    node_meta: dict[str, object] | None
    config_meta: dict[str, object] | None
    bounded: str
    expected_error_fragment: str
    expected_code: str


@dataclass(frozen=True)
class DbtDiffExecuteTestCase:
    description: str
    options_args: tuple[str, ...]
    current_rows: tuple[tuple[object, ...], ...]
    reuse_rows: tuple[tuple[object, ...], ...]
    node_resource_type: str
    expected_model_names: tuple[str, ...]
    expected_has_row_result: bool
    expected_unequal_count: int
    expected_left_only_count: int
    expected_right_only_count: int
    expected_has_failures: bool


@dataclass(frozen=True)
class DbtDiffExecuteErrorTestCase:
    description: str
    schema_only: bool
    create_current_relation: bool
    create_reuse_relation: bool
    expected_error_fragment: str
    expected_code: str


@dataclass(frozen=True)
class DbtSqlTestTargetTestCase:
    description: str
    selected_dbt_unique_ids: tuple[str, ...]
    select: tuple[str, ...]
    expected_target_names: tuple[str, ...]
    expected_model_names: tuple[str, ...]
    expected_query_fragments: tuple[str, ...]
    manifest_factory: Callable[[], DbtManifestIndex]
    expected_adapted_model_names: tuple[str, ...] | None = None
    expected_absent_fragments: tuple[str, ...] = field(default_factory=tuple)
    sqlbuild_model_names: tuple[str, ...] = field(default_factory=tuple)
    mock_model_names: tuple[str, ...] = field(default_factory=tuple)

    @property
    def adapted_model_names(self) -> tuple[str, ...]:
        return self.expected_adapted_model_names or self.expected_model_names


@dataclass(frozen=True)
class DbtSqlTestMultipleBoundaryTestCase:
    description: str
    expected_test_model_names: tuple[tuple[str, ...], ...]
    expected_query_fragments_by_test: tuple[tuple[str, ...], ...]
    expected_absent_fragments_by_test: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class DbtSqlTestTargetErrorTestCase:
    description: str
    manifest_factory: Callable[[], DbtManifestIndex]
    project_factory: Callable[[], CompiledProject]
    expected_model_names: tuple[str, ...]
    target_names: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class DbtSqlTestFixtureNameTestCase:
    description: str
    manifest_factory: Callable[[], DbtManifestIndex]
    fixture_resolver: Callable[[DbtManifestIndex, set[str]], set[str]]
    known_names: set[str]
    expected_names: set[str]
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class DbtSeedIdentityTestCase:
    description: str
    checksum: str
    config_overrides: dict[str, object] | None
    other_checksum: str
    other_config_overrides: dict[str, object] | None
    expected_same_identity: bool


@dataclass(frozen=True)
class DbtSeedContentIdentityTestCase:
    description: str
    left_content: str
    right_content: str
    expected_same_identity: bool
    expected_warning: bool
