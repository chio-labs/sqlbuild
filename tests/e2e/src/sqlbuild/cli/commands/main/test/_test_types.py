"""Test types for test command e2e tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SqlTestE2ETestCase:
    """Test case for sqb test e2e verification."""

    description: str
    expected_exit_code: int
    expected_stdout_fragment: str


@dataclass(frozen=True)
class SqlglotChainSqlTestE2ETestCase:
    """Test case for SQLGlot SQL unit-test chain execution and artifacts."""

    description: str
    sqlglot_enabled: bool
    expected_artifact_fragments: tuple[str, ...]
    unexpected_artifact_fragments: tuple[str, ...]
