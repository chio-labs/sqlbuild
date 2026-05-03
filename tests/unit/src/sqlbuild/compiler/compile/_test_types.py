from dataclasses import dataclass


@dataclass(frozen=True)
class BuildCompileInputsTestCase:
    description: str
    repo_files: dict[str, str]
    expected_model_schema_names: tuple[str | None, ...]
    expected_model_config_values: tuple[dict[str, object], ...]
    expected_model_path_defaults: tuple[str | None, ...]
    expected_seed_names: tuple[str, ...]
    expected_source_names: tuple[str, ...]


@dataclass(frozen=True)
class BuildCompileInputsErrorTestCase:
    description: str
    repo_files: dict[str, str]
    expected_error_fragment: str
