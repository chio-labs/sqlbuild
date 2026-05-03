from dataclasses import dataclass


@dataclass(frozen=True)
class LoadProjectConfigTestCase:
    description: str
    project_file_contents: str
    expected_name: str
    expected_adapter: str
    expected_default_environment: str
    expected_connection: dict[str, str]
    expected_sqlglot: bool
    expected_materialized: str
    expected_row_diff_exclude_columns: tuple[str, ...]
    expected_path_default_schema: str
    expected_vars: dict[str, str]
    expected_dev_schema: str
    expected_allow_as_source: bool
    expected_retention_days: int


@dataclass(frozen=True)
class LoadLocalConfigTestCase:
    description: str
    repo_files: dict[str, str]
    expected_environment: str | None
    expected_vars: dict[str, str]


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


@dataclass(frozen=True)
class ParseSourcesYamlErrorTestCase:
    description: str
    contents: str
    expected_error_fragment: str
