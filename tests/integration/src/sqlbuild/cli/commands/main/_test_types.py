from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadCommandIntegrationTestCase:
    description: str
    project_files: dict[str, str]
    expected_exit_code: int
    expected_rows: tuple[tuple[object, ...], ...]
    expected_stdout_fragment: str
    expected_stdout_absent_fragments: tuple[str, ...] = ()
    select: tuple[str, ...] = ()
