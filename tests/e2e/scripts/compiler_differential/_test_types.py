"""Test case types for the compiler differential harness end-to-end tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HarnessRunTestCase:
    """One harness run over a fixture and the report lines it must and must not print."""

    description: str
    extra_arguments: tuple[str, ...]
    expected_exit_code: int
    expected_lines: tuple[str, ...]
    expected_patterns: tuple[str, ...]
    expected_absent: tuple[str, ...]


@dataclass(frozen=True)
class ProjectExpectationTestCase:
    """A broken project run with one --expect value and the verdict the harness must reach."""

    description: str
    extra_arguments: tuple[str, ...]
    expected_exit_code: int
    expected_lines: tuple[str, ...]
