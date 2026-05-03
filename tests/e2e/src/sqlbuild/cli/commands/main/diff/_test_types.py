"""Test types for diff e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiffCommandE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_stderr_fragments: tuple[str, ...] = field(default_factory=tuple)
    mutation_sql: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiffKeyFailureE2ETestCase:
    description: str
    mutation_sql: tuple[str, ...]
    expected_stderr_fragment: str
