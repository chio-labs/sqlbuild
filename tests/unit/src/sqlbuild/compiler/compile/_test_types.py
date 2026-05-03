from dataclasses import dataclass, field


@dataclass(frozen=True)
class BuildCompileInputsTestCase:
    description: str
    repo_files: dict[str, str]
    selected_environment: str | None
    cli_vars: dict[str, str] | None
    run_id: str | None
    expected_model_schema_names: tuple[str | None, ...]
    expected_model_config_values: tuple[dict[str, object], ...]
    expected_model_path_defaults: tuple[str | None, ...]
    expected_seed_names: tuple[str, ...]
    expected_source_names: tuple[str, ...]
    expected_effective_environment_name: str | None
    expected_effective_connection: dict[str, object]
    expected_effective_vars: dict[str, str]
    environment_variables: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildCompileInputsErrorTestCase:
    description: str
    repo_files: dict[str, str]
    selected_environment: str | None
    run_id: str | None
    expected_error_fragment: str
    environment_variables: dict[str, str] = field(default_factory=dict)
