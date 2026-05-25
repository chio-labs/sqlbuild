from dataclasses import dataclass, field


@dataclass(frozen=True)
class BuildCompileInputsTestCase:
    description: str
    repo_files: dict[str, str]
    selected_environment: str | None
    cli_vars: dict[str, object] | None
    run_id: str | None
    expected_model_schema_names: tuple[str | None, ...]
    expected_model_config_values: tuple[dict[str, object], ...]
    expected_model_path_defaults: tuple[str | None, ...]
    expected_seed_names: tuple[str, ...]
    expected_source_names: tuple[str, ...]
    expected_effective_environment_name: str | None
    expected_effective_connection: dict[str, object]
    expected_effective_vars: dict[str, object]
    expected_source_expressions: tuple[str | None, ...] | None = None
    expected_source_relations: tuple[tuple[str | None, str | None, str | None], ...] | None = None
    expected_model_schema_descriptions: tuple[str | None, ...] | None = None
    expected_model_column_metadata: (
        tuple[
            tuple[
                tuple[
                    str,
                    str | None,
                    str | None,
                    tuple[tuple[str, dict[str, object]], ...],
                ],
                ...,
            ],
            ...,
        ]
        | None
    ) = None
    expected_effective_sqlglot: bool = True
    expected_effective_sql_validation: bool = True
    expected_effective_max_concurrency: int = 1
    expected_model_query_sqls: tuple[str, ...] = field(default_factory=tuple)
    expected_model_column_nullables: tuple[tuple[bool | None, ...], ...] | None = None
    expected_test_sql_bodies: tuple[str, ...] = field(default_factory=tuple)
    expected_test_authored_cte_names: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    expected_test_mock_model_names: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    expected_test_mock_source_names: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    expected_test_mock_seed_names: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    expected_test_expected_model_names: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    expected_audit_sql_bodies: tuple[str, ...] = field(default_factory=tuple)
    expected_diagnostic_codes: tuple[str, ...] = field(default_factory=tuple)
    expected_diagnostic_messages: tuple[str, ...] = field(default_factory=tuple)
    expected_sql_function_names: tuple[str, ...] = field(default_factory=tuple)
    expected_sql_function_arguments: tuple[tuple[tuple[str, str], ...], ...] = field(
        default_factory=tuple
    )
    expected_sql_function_returns: tuple[str, ...] = field(default_factory=tuple)
    expected_sql_function_return_columns: tuple[tuple[tuple[str, str], ...], ...] = field(
        default_factory=tuple
    )
    expected_sql_function_body_sqls: tuple[str, ...] = field(default_factory=tuple)
    expected_sql_function_databases: tuple[str | None, ...] = field(default_factory=tuple)
    expected_sql_function_schemas: tuple[str | None, ...] = field(default_factory=tuple)
    expected_sql_function_languages: tuple[str, ...] = field(default_factory=tuple)
    expected_sql_function_runtime_versions: tuple[str | None, ...] = field(default_factory=tuple)
    expected_sql_function_entry_points: tuple[str | None, ...] = field(default_factory=tuple)
    expected_sql_function_packages: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    expected_sql_function_query_change_backfills: tuple[str | None, ...] = field(
        default_factory=tuple
    )
    expected_model_references: tuple[tuple[tuple[str, str], ...], ...] = field(
        default_factory=tuple
    )
    expected_audit_references: tuple[tuple[tuple[str, str], ...], ...] = field(
        default_factory=tuple
    )
    environment_variables: dict[str, str] = field(default_factory=dict)
    no_sql_validation: bool = False


@dataclass(frozen=True)
class BuildCompileInputsErrorTestCase:
    description: str
    repo_files: dict[str, str]
    selected_environment: str | None
    run_id: str | None
    expected_error_fragment: str
    expected_error_type: type[Exception] = ValueError
    environment_variables: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildEffectiveRuntimeConfigTestCase:
    description: str
    selected_environment: str | None
    cli_vars: dict[str, object] | None
    expected_environment_name: str | None
    expected_vars: dict[str, object]


@dataclass(frozen=True)
class SeedRefRegressionTestCase:
    description: str
    repo_files: dict[str, str]
    expected_model_count: int


@dataclass(frozen=True)
class ResolveEnvironmentConfigTestCase:
    description: str
    expected_connection: dict[str, object]
    expected_vars: dict[str, object]
    expected_database: str
    expected_schema: str
    expected_allow_as_source: bool
    expected_allow_as_target: bool


@dataclass(frozen=True)
class CursorStartCompileInputsTestCase:
    description: str
    repo_files: dict[str, str]
    expected_cursor_start: str | int


@dataclass(frozen=True)
class CursorStartCompileErrorTestCase:
    description: str
    repo_files: dict[str, str]
    expected_error_fragment: str
