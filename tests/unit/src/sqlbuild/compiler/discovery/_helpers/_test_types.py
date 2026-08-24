from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class DeferredModelOutputLocationTestCase:
    description: str
    expected_extract_implicit_alias_columns: bool


@dataclass(frozen=True)
class ValidatePathDefaultsMatchModelsTestCase:
    description: str
    model_relative_paths: tuple[str, ...]
    path_defaults: dict[str, dict[str, object]]
    expected_model_file_count: int


@dataclass(frozen=True)
class LoadProjectConfigTestCase:
    description: str
    project_file_contents: str
    expected_name: str
    expected_adapter: str
    expected_default_target: str
    expected_connection: dict[str, str]
    expected_sql_analysis: bool
    expected_max_concurrency: int
    expected_materialized: str | None
    expected_row_diff_exclude_columns: tuple[str, ...]
    expected_row_diff_tolerances: dict[str, object]
    expected_contract: str | None
    expected_path_defaults: dict[str, dict[str, object]]
    expected_vars: dict[str, str]
    expected_targets: dict[str, dict[str, object]]
    expected_janitor_enabled: bool
    expected_retention_days: int
    expected_janitor_max_checkpoints: int
    expected_janitor_delete_tracked_only: bool
    expected_janitor_exclude_patterns: tuple[str, ...]
    expected_janitor_direct_state_history_versions: int = 20
    expected_current_state_full_refresh: str = "deny"
    expected_historical_full_refresh: str = "require_confirmation"
    expected_snapshot_schema_change: str = "append_new_columns"
    expected_wildcard_check_schema_change: str = "require_confirmation"
    expected_scenario_local_type_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    expected_snapshot_limits: dict[str, int | None] = field(
        default_factory=lambda: {
            "max_rows_per_relation": None,
            "max_total_rows": None,
            "max_bytes_per_relation": None,
            "max_total_bytes": None,
        }
    )
    expected_dbt_project_dir: str | None = None
    expected_dbt_profiles_dir: str | None = None
    expected_dbt_target: str | None = None
    expected_dbt_target_path: str | None = None
    expected_dbt_vars: dict[str, object] = field(default_factory=dict)
    expected_auto_load_sources: bool = True
    expected_virtual_environments: bool = False
    expected_changes_only: bool = False


@dataclass(frozen=True)
class LoadLocalConfigTestCase:
    description: str
    repo_files: dict[str, str]
    expected_target: str | None
    expected_adapter: str | None
    expected_connection: dict[str, object]
    expected_sql_analysis: bool
    expected_sql_validation: bool
    expected_max_concurrency: int
    expected_setting_overrides: frozenset[str]
    expected_vars: dict[str, str]
    expected_dbt_target: str | None = None
    expected_dbt_vars: dict[str, object] = field(default_factory=dict)
    expected_auto_load_sources: bool = True
    expected_changes_only: bool = False
    expected_targets: dict[str, dict[str, object]] = field(default_factory=dict)
    expected_missing_attributes: tuple[str, ...] = ()
    expected_scenario_local_type_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    expected_snapshot_limits: dict[str, int | None] = field(
        default_factory=lambda: {
            "max_rows_per_relation": None,
            "max_total_rows": None,
            "max_bytes_per_relation": None,
            "max_total_bytes": None,
        }
    )


@dataclass(frozen=True)
class LoadProjectConfigErrorTestCase:
    description: str
    project_file_contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class LoadProjectCostConfigTestCase:
    description: str
    project_file_contents: str
    expected_usd_per_credit: Decimal
    expected_is_default: bool


@dataclass(frozen=True)
class LoadProjectCostConfigErrorTestCase:
    description: str
    value: str
    expected_error_fragment: str


@dataclass(frozen=True)
class LoadLocalConfigErrorTestCase:
    description: str
    local_file_contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class DiscoverHookFunctionsTestCase:
    description: str
    repo_files: dict[str, str]
    expected_hook_names: tuple[str, ...]
    expected_hook_paths: tuple[str, ...]
    expected_hook_descriptions: tuple[str | None, ...]
    expected_function_names: tuple[str, ...]
    expected_marker_file_exists: bool = False


@dataclass(frozen=True)
class DiscoverHookFunctionsErrorTestCase:
    description: str
    repo_files: dict[str, str]
    expected_error_fragment: str


@dataclass(frozen=True)
class DiscoverProviderClassesTestCase:
    description: str
    repo_files: dict[str, str]
    expected_provider_names: tuple[str, ...]
    expected_provider_paths: tuple[str, ...]
    expected_provider_class_names: tuple[str, ...]
    expected_marker_file_exists: bool = False


@dataclass(frozen=True)
class DiscoverProviderCacheIsolationTestCase:
    description: str
    first_repo_files: dict[str, str]
    second_repo_files: dict[str, str]
    expected_first_provider_names: tuple[str, ...]
    expected_second_provider_names: tuple[str, ...]


@dataclass(frozen=True)
class DiscoverProviderClassesErrorTestCase:
    description: str
    repo_files: dict[str, str]
    expected_error_fragment: str


@dataclass(frozen=True)
class DiscoverProviderEnvSettingsTestCase:
    description: str
    repo_files: dict[str, str]
    env_name: str
    env_value: str
    expected_provider_name: str
    expected_field_name: str
    expected_field_value: object


@dataclass(frozen=True)
class DiscoverProviderSecretErrorTestCase:
    description: str
    repo_files: dict[str, str]
    env_name: str
    env_value: str
    expected_error_fragment: str
    unexpected_error_fragment: str


@dataclass(frozen=True)
class ParseModelSqlHeaderTestCase:
    description: str
    contents: str
    expected_header_values: dict[str, object]
    expected_query: str


@dataclass(frozen=True)
class ParseModelSqlErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ParseDeclarationFileTestCase:
    description: str
    contents: str
    expected_names: tuple[str, ...]
    expected_scalar_types: tuple[str, ...]
    expected_values: tuple[tuple[str | int, ...], ...]


@dataclass(frozen=True)
class ParseDeclarationFileErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ParseModelSchemaDeclarationTestCase:
    description: str
    contents: str
    expected_names: tuple[str, ...]
    expected_description: str
    expected_parent: str
    expected_base_column_names: tuple[str, ...]
    expected_base_column_line: int
    expected_child_column_line: int
    expected_audit_names: tuple[str, ...]


@dataclass(frozen=True)
class ModelHeaderColumnLocationTestCase:
    description: str
    contents: str
    expected_locations: dict[str, tuple[Path, int, int, int | None, int | None]]


@dataclass(frozen=True)
class ModelOutputColumnLocationTestCase:
    description: str
    contents: str
    expected_locations: dict[str, tuple[Path, int, int, int | None, int | None]]
    extract_implicit_alias_columns: bool = True


@dataclass(frozen=True)
class ParseSqlTestFileTestCase:
    description: str
    contents: str
    expected_names: tuple[str | None, ...]
    expected_sql_bodies: tuple[str, ...]
    expected_test_indexes: tuple[int, ...]


@dataclass(frozen=True)
class ParseSqlTestFileErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ParseSqlScenarioFileTestCase:
    description: str
    contents: str
    expected_name: str
    expected_header_values: dict[str, object]
    expected_sql_body: str


@dataclass(frozen=True)
class ParseSqlScenarioFileErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ParseSourcesYamlDltTestCase:
    description: str
    contents: str
    expected_source_names: tuple[str, ...]
    expected_loaders: tuple[str, ...]
    expected_kind: str
    expected_dlt_names: tuple[str, ...]
    expected_schemas: tuple[str | None, ...]
    expected_destination_config: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParseSqlAuditFileTestCase:
    description: str
    contents: str
    expected_names: tuple[str | None, ...]
    expected_sql_bodies: tuple[str, ...]
    expected_audit_indexes: tuple[int, ...]


@dataclass(frozen=True)
class ParseSqlAuditFileErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ParseSchemaYamlTestCase:
    description: str
    contents: str
    expected_model_names: tuple[str, ...]
    expected_seed_names: tuple[str, ...]
    expected_model_column_names: tuple[tuple[str, ...], ...]
    expected_seed_column_names: tuple[tuple[str, ...], ...]
    expected_model_audit_names: tuple[tuple[str, ...], ...]
    expected_column_audit_names: tuple[tuple[tuple[str, ...], ...], ...]
    expected_model_column_nullables: tuple[tuple[bool | None, ...], ...] | None = None
    expected_seed_column_nullables: tuple[tuple[bool | None, ...], ...] | None = None
    expected_seed_databases: tuple[str | None, ...] = ()
    expected_seed_schemas: tuple[str | None, ...] = ()


@dataclass(frozen=True)
class ParseSchemaYamlErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ParseSeedCsvSettingsYamlTestCase:
    description: str
    contents: str
    expected_delimiter: str | None
    expected_quotechar: str | None
    expected_doublequote: bool | None
    expected_escapechar: str | None
    expected_skipinitialspace: bool | None
    expected_lineterminator: str | None
    expected_encoding: str | None
    expected_na_values: tuple[object, ...] | dict[str, tuple[object, ...]] | None
    expected_keep_default_na: bool | None


@dataclass(frozen=True)
class DiscoverProjectInputsErrorTestCase:
    description: str
    repo_files: dict[str, str]
    expected_error_fragment: str


@dataclass(frozen=True)
class ParseSourcesYamlTestCase:
    description: str
    contents: str
    expected_source_names: tuple[str, ...]
    expected_column_names: tuple[tuple[str, ...], ...]
    expected_type_enforcement_values: tuple[bool | None, ...]
    expected_contract_values: tuple[str | None, ...]
    expected_expressions: tuple[str | None, ...]
    expected_loaders: tuple[str | None, ...] | None = None
    expected_write_strategies: tuple[str | None, ...] | None = None
    expected_load_batch_sizes: tuple[int | None, ...] | None = None
    expected_cursor_columns: tuple[str | None, ...] | None = None
    expected_unique_keys: tuple[tuple[str, ...], ...] | None = None
    expected_freshness_strategies: tuple[str | None, ...] | None = None
    expected_freshness_value_kinds: tuple[str | None, ...] | None = None
    expected_freshness_columns: tuple[str | None, ...] | None = None
    expected_freshness_queries: tuple[str | None, ...] | None = None
    expected_freshness_filters: tuple[str | None, ...] | None = None
    expected_freshness_lag_tolerances: tuple[str | None, ...] | None = None
    expected_freshness_age_policy_warn_afters: tuple[str | None, ...] | None = None
    expected_freshness_age_policy_error_afters: tuple[str | None, ...] | None = None
    expected_source_audit_names: tuple[tuple[str, ...], ...] = ()
    expected_column_audit_names: tuple[tuple[tuple[str, ...], ...], ...] = ()
    expected_column_nullables: tuple[tuple[bool | None, ...], ...] | None = None


@dataclass(frozen=True)
class ParseSourcesYamlErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ParseSourcesYamlIngestrTestCase:
    description: str
    contents: str
    expected_loader: str
    expected_kind: str
    expected_primary_key: tuple[str, ...]
    expected_extra_args: tuple[str, ...]


@dataclass(frozen=True)
class DiscoverMaterializationFilesTestCase:
    description: str
    files: dict[str, str]
    expected_names: tuple[str, ...]


@dataclass(frozen=True)
class DiscoverLoaderFunctionsTestCase:
    description: str
    files: dict[str, str]
    expected_names: tuple[str, ...]
    expected_targets: tuple[str | None, ...]
    expected_dependency_counts: tuple[int, ...]
    expected_write_strategies: tuple[str | None, ...] = ()
    expected_cursor_columns: tuple[str | None, ...] = ()
    expected_unique_keys: tuple[tuple[str, ...], ...] = ()
    expected_column_names: tuple[tuple[str, ...], ...] = ()
    expected_contracts: tuple[str | None, ...] = ()
    expected_error_fragment: str = ""


@dataclass(frozen=True)
class DiscoverPythonNodeFactoriesTestCase:
    description: str
    files: dict[str, str]
    expected_loader_names: tuple[str, ...]
    expected_task_names: tuple[str, ...]
    expected_asset_names: tuple[str, ...]
    expected_check_names: tuple[str, ...]
    expected_loader_dependency_counts: tuple[int, ...] = ()
    expected_task_dependency_counts: tuple[int, ...] = ()
    expected_asset_dependency_counts: tuple[int, ...] = ()
    expected_check_dependency_counts: tuple[int, ...] = ()
    expected_error_fragment: str = ""


@dataclass(frozen=True)
class DiscoverTaskAssetFunctionsTestCase:
    description: str
    files: dict[str, str]
    expected_task_names: tuple[str, ...]
    expected_task_dependency_counts: tuple[int, ...]
    expected_task_tags: tuple[tuple[str, ...], ...]
    expected_asset_names: tuple[str, ...]
    expected_asset_dependency_counts: tuple[int, ...]
    expected_asset_column_names: tuple[tuple[str, ...], ...]
    expected_asset_lineage_columns: tuple[tuple[str, ...], ...]
    expected_error_fragment: str = ""


@dataclass(frozen=True)
class DiscoverCheckFunctionsTestCase:
    description: str
    files: dict[str, str]
    expected_check_names: tuple[str, ...]
    expected_check_dependency_counts: tuple[int, ...]
    expected_check_severities: tuple[str, ...]
    expected_check_tags: tuple[tuple[str, ...], ...]
