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


@dataclass(frozen=True)
class VirtualDiffE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_stderr_fragments: tuple[str, ...] = field(default_factory=tuple)
    unexpected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiffSamplingPrecedenceE2ETestCase:
    description: str
    project_limit: int
    project_seed: int
    path_limit: int
    path_seed: int
    model_limit: int
    model_seed: int
    cli_limit: int
    cli_seed: int
    expected_model_scope: str
    expected_model_exhaustive_scope: str
    expected_path_scope: str
    expected_project_scope: str
    expected_cli_scope: str
    expected_exhaustive_scope: str


@dataclass(frozen=True)
class DiffSamplingSeedE2ETestCase:
    description: str
    row_limit: int
    repeated_seed: int
    alternate_seed: int
    expected_membership_count: int


@dataclass(frozen=True)
class DiffJsonOutputE2ETestCase:
    description: str
    row_limit: int
    seed: int
    expected_status: str
    expected_scope: str
    expected_population: int
    expected_compared: int
