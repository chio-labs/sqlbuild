"""Test types for janitor e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class JanitorDisabledE2ETestCase:
    """Test case for disabled janitor command behavior."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]


@dataclass(frozen=True)
class JanitorCleanupE2ETestCase:
    """Test case for tracked-only janitor cleanup behavior."""

    description: str
    build_command: tuple[str, ...]
    janitor_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_existing_tables: tuple[str, ...]
    expected_missing_tables: tuple[str, ...]


@dataclass(frozen=True)
class JanitorInvalidConfigE2ETestCase:
    """Test case for invalid janitor config behavior."""

    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stderr_fragments: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
