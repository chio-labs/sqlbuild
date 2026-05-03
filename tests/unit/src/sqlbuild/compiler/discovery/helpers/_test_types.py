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
    local_file_contents: str | None
    expected_environment: str | None
    expected_vars: dict[str, str]
