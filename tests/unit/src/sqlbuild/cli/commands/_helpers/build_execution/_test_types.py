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


@dataclass(frozen=True)
class BuildPhaseTimingsTestCase:
    description: str
    expected_output: str


@dataclass(frozen=True)
class CostFailureTimingTestCase:
    description: str
    clock_values: tuple[float, ...]
    expected_cost_seconds: float
    expected_error_message: str
