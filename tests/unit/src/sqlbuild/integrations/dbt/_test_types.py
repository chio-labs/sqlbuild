from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtInteropParsedArgs,
    DbtLsNode,
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
class DbtExecutionSelectionStatusTestCase:
    description: str
    expected_total: int
    expected_output_fragment: str
    expected_completion_fragment: str


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
class DbtArgRoutingTestCase:
    description: str
    command: str
    parsed: DbtInteropParsedArgs
    expected_select: tuple[str, ...]
    expected_exclude: tuple[str, ...]
    expected_dbt_args: tuple[str, ...]
    expected_sqlbuild_args: tuple[str, ...]


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
