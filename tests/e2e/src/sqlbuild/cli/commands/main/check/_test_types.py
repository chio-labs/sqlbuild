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
    project_kind: str = "standard"
    initialize_state: bool = False
    expected_file_fragments: tuple[tuple[str, tuple[str, ...]], ...] = ()
