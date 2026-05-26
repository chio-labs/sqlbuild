from dataclasses import dataclass, field
from pathlib import Path


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
    expected_default_environment: str
    expected_connection: dict[str, str]
    expected_sqlglot: bool
    expected_max_concurrency: int
    expected_materialized: str
    expected_row_diff_exclude_columns: tuple[str, ...]
    expected_row_diff_tolerances: dict[str, object]
    expected_contract: str | None
    expected_path_default_schema: str
    expected_vars: dict[str, str]
    expected_dev_connection: dict[str, object]
    expected_dev_vars: dict[str, str]
    expected_dev_schema: str
    expected_dev_defer_sources_to: str | None
    expected_allow_as_source: bool
    expected_janitor_enabled: bool
    expected_retention_days: int
    expected_janitor_delete_tracked_only: bool
    expected_janitor_exclude_patterns: tuple[str, ...]
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
    expected_auto_load_sources: bool = True


@dataclass(frozen=True)
class LoadLocalConfigTestCase:
    description: str
    repo_files: dict[str, str]
    expected_environment: str | None
    expected_adapter: str | None
    expected_connection: dict[str, object]
    expected_sqlglot: bool
    expected_sql_validation: bool
    expected_max_concurrency: int
    expected_setting_overrides: frozenset[str]
    expected_vars: dict[str, str]
    expected_auto_load_sources: bool = True
    expected_environments: dict[str, dict[str, object]] = field(default_factory=dict)
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
class LoadLocalConfigErrorTestCase:
    description: str
    local_file_contents: str
    expected_error_fragment: str


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
class ModelHeaderColumnLocationTestCase:
    description: str
    contents: str
    expected_locations: dict[str, tuple[Path, int, int, int | None, int | None]]


@dataclass(frozen=True)
class ModelOutputColumnLocationTestCase:
    description: str
    contents: str
    expected_locations: dict[str, tuple[Path, int, int, int | None, int | None]]
    sqlglot_enabled: bool = True


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
