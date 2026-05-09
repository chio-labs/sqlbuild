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
