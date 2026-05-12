"""Test types for scenario command e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScenarioCliE2ETestCase:
    """Test case for sqb scenario command e2e verification."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_stderr_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_retained_prefix_count: int | None = None


@dataclass(frozen=True)
class ScenarioRuntimeArtifactTestCase:
    """Test case for scenario target/run artifact verification."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    artifact_relative_path: Path
    expected_artifact_fragments: tuple[str, ...]


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
