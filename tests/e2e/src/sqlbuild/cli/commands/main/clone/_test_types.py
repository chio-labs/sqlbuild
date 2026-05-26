from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CloneE2ETestCase:
    description: str
    repo_files: dict[str, str]
    clone_command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]


@dataclass(frozen=True)
class VirtualCloneE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_exit_code: int
    expected_stdout_fragments: tuple[str, ...]
