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
