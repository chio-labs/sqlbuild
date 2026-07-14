from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

type SelectionStalenessRows = tuple[tuple[object, ...], ...]
type SelectionStalenessFiles = tuple[tuple[str, str], ...]


class SelectionStalenessRunner(Protocol):
    def __call__(
        self,
        *,
        tmp_path: Path,
        test_case: SelectionStalenessEngineE2ETestCase,
    ) -> None: ...


@dataclass(frozen=True)
class SelectionStalenessEngineE2ETestCase:
    description: str
    project_name: str
    graph: str
    runner: SelectionStalenessRunner
    baseline_files: SelectionStalenessFiles
    mutated_files: SelectionStalenessFiles
    baseline_command: tuple[str, ...]
    exact_commands: tuple[tuple[str, ...], ...]
    repair_command: tuple[str, ...]
    expected_exact_stdout_fragments: tuple[str, ...]
    unexpected_exact_stdout_fragments: tuple[str, ...]
    expected_repair_stdout_fragments: tuple[str, ...]
    unexpected_repair_stdout_fragments: tuple[str, ...]
    expected_rows_after_baseline: SelectionStalenessRows
    expected_rows_after_exact_commands: tuple[SelectionStalenessRows, ...]
    expected_rows_after_repair: SelectionStalenessRows
    database_relative_path: Path
    fact_rows_query: str
    notes: str = ""
