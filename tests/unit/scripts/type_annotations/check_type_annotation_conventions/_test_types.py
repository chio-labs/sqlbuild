"""Local test types for type-annotation checker tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckPathsTestCase:
    """One type-checker test case."""

    description: str
    repo_files: dict[str, str]
    expected_violation_codes: tuple[str, ...]


@dataclass(frozen=True)
class CheckCliMainTestCase:
    """One type-checker CLI test case."""

    description: str
    repo_files: dict[str, str]
    cli_paths: tuple[str, ...]
    expected_exit_code: int
