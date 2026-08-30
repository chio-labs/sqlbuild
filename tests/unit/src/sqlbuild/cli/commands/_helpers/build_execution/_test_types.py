from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.cli.commands.models import SelectorFileSummary


@dataclass(frozen=True)
class BuildRunContextTestCase:
    description: str
    connection_config: dict[str, object]
    effective_vars: dict[str, object]
    selector_files: tuple[SelectorFileSummary, ...]
    full_refresh: bool
    expected_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]
    selected_source_count: int = 0
    selected_python_count: int = 0
    total_source_count: int = 0
    total_task_count: int = 0
