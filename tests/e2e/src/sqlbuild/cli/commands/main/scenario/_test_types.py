"""Test types for scenario command e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScenarioNamespaceE2ETestCase:
    description: str
    namespace_a: str = "job-a"
    namespace_b: str = "job-b"
    expected_total: int = 15
    expected_other_total: int = 27
    expected_exit_code: int = 0
    expected_relation_count: int = 3
    expected_error: str = "C458"


@dataclass(frozen=True)
class ScenarioNamespaceSourceE2ETestCase:
    description: str
    expected_namespace: str | None
    expected_source: str
    project_config: str = ""
    local_config: str = ""
    environment: tuple[tuple[str, str], ...] = ()
    cli_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioCliE2ETestCase:
    """Test case for sqb scenario command e2e verification."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_stderr_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_retained_prefix_count: int | None = None
    disabled_setting: str | None = None


@dataclass(frozen=True)
class ScenarioPartialFixtureE2ETestCase:
    """Test case for implicit partial fixture completion in a scenario."""

    description: str
    repo_files: dict[str, str]
    expected_stdout_fragment: str
    expected_artifact_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioRuntimeArtifactTestCase:
    """Test case for scenario target/run artifact verification."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    artifact_relative_path: Path
    expected_artifact_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioPythonHooksCliE2ETestCase:
    """Test case for scenario CLI execution with Python lifecycle hooks."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_hook_log_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ScenarioLocalRuntimeArtifactTestCase:
    """Test case for local scenario target/run artifact verification."""

    description: str
    scenario_name: str
    capture_command: tuple[str, ...]
    command: tuple[str, ...]
    expected_exit_code: int
    artifact_relative_path: Path
    expected_artifact_fragments: tuple[str, ...]
    additional_project_files: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ScenarioLocalCliE2ETestCase:
    """Test case for sqb scenario test --local verification."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioLocalRetainE2ETestCase:
    """Test case for retained local scenario DuckDB verification."""

    description: str
    scenario_name: str
    capture_command: tuple[str, ...]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    retained_duckdb_relative_path: Path
    retained_count_sql: str
    expected_count: int
    retained_rows_sql: str | None = None
    expected_rows: tuple[tuple[object, ...], ...] = ()
    expected_duckdb_exists: bool = True
    corrupt_jsonl: bool = False
    corrupt_capture_dialect: bool = False
    additional_project_files: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ScenarioLocalSnapshotSyncE2ETestCase:
    """Test case for local snapshot sync and refresh verification."""

    description: str
    scenario_name: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    initial_capture: bool = False
    corrupt_jsonl: bool = False
    update_scenario_after_capture: bool = False
    expected_duckdb_exists: bool = True
    query_when_exists: bool = True
    expected_count: int = 2


@dataclass(frozen=True)
class ScenarioLocalCommittedSnapshotE2ETestCase:
    """Test case for local replay from a pre-written snapshot fixture."""

    description: str
    scenario_name: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    unexpected_stdout_fragments: tuple[str, ...]
    retained_duckdb_relative_path: Path
    retained_count_sql: str
    expected_count: int
    retained_rows_sql: str
    expected_rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class ScenarioAuthoredCheckSqlE2ETestCase:
    """Scenario whose check SQL uses DuckDB syntax a generic regeneration cannot parse."""

    description: str
    scenario_sql: str
    expected_stdout_fragment: str


@dataclass(frozen=True)
class ScenarioUnresolvableCheckSqlE2ETestCase:
    """Scenario whose check SQL contains an unclosed string in the target dialect."""

    description: str
    scenario_sql: str
    expected_output_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioLocalReplayProjectDialectE2ETestCase:
    """Project-dialect scenario SQL replayed locally from a captured snapshot."""

    description: str
    scenario_name: str
    source_fixture_sql: str
    assertion_sql: str
    expected_stdout_fragment: str


@dataclass(frozen=True)
class ScenarioPromotionE2ETestCase:
    """Test case for scenario table promotion matching build configuration."""

    description: str
    defaults_config: str
    settings_config: str
    model_columns: str
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expect_staged_promotion: bool
    unexpected_stdout_fragments: tuple[str, ...] = ("K011", "R004")


@dataclass(frozen=True)
class ScenarioConcurrencyE2ETestCase:
    """Test case for concurrent scenario execution through the CLI."""

    description: str
    command_args: tuple[str, ...]
    settings_config: str
    expected_header: str


@dataclass(frozen=True)
class ScenarioEmptyFixtureE2ETestCase:
    """Test case for `__empty_fixture()` mocks inside SQL scenarios."""

    description: str
    customer_columns_yaml: str
    expected_exit_code: int
    expected_fragments: tuple[str, ...]
