"""Test case types for sqb check e2e tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckCommandTestCase:
    """Expected outcome for one sqb check invocation."""

    description: str
    command: tuple[str, ...]
    expected_returncode: int
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...] = ()
    project_kind: str = "direct"
    initialize_state: bool = False
    expected_file_fragments: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class ReadSidePythonCheckCommandTestCase:
    """Expected outcome for a read-side Python check lifecycle."""

    description: str
    missing_command: tuple[str, ...]
    build_command: tuple[str, ...]
    check_command: tuple[str, ...]
    expected_missing_returncode: int
    expected_build_returncode: int
    expected_check_returncode: int
    expected_missing_fragments: tuple[str, ...]
    expected_check_fragments: tuple[str, ...]
