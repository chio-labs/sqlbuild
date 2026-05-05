from dataclasses import dataclass, field


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
    expected_path_default_schema: str
    expected_vars: dict[str, str]
    expected_dev_connection: dict[str, object]
    expected_dev_vars: dict[str, str]
    expected_dev_schema: str
    expected_allow_as_source: bool
    expected_janitor_enabled: bool
    expected_retention_days: int
    expected_janitor_delete_tracked_only: bool
    expected_janitor_exclude_patterns: tuple[str, ...]


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
    expected_environments: dict[str, dict[str, object]] = field(default_factory=dict)
    expected_missing_attributes: tuple[str, ...] = ()


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
    expected_expressions: tuple[str | None, ...]
    expected_source_audit_names: tuple[tuple[str, ...], ...] = ()
    expected_column_audit_names: tuple[tuple[tuple[str, ...], ...], ...] = ()


@dataclass(frozen=True)
class ParseSourcesYamlErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class DiscoverMaterializationFilesTestCase:
    description: str
    files: dict[str, str]
    expected_names: tuple[str, ...]
