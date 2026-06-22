from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

type SelectionStalenessEngine = Literal["native", "dbt"]


@dataclass(frozen=True)
class SelectionStalenessEngineOverride:
    description: str = "engine override"
    exact_command: tuple[str, ...] | None = None
    repair_command: tuple[str, ...] | None = None
    expected_exact_stdout_fragments: tuple[str, ...] | None = None
    unexpected_exact_stdout_fragments: tuple[str, ...] | None = None
    expected_repair_stdout_fragments: tuple[str, ...] | None = None
    unexpected_repair_stdout_fragments: tuple[str, ...] | None = None
    xfail_reason: str | None = None


@dataclass(frozen=True)
class SelectionStalenessE2ETestCase:
    description: str
    project_name: str
    scenario: str
    graph: str
    exact_command: tuple[str, ...] = field(default_factory=tuple)
    repair_command: tuple[str, ...] = field(default_factory=tuple)
    expected_exact_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    unexpected_exact_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_repair_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    unexpected_repair_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_rows_after_baseline: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_rows_after_exact: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_rows_after_second_exact: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_rows_after_repair: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    leaf_materialization: str = "table"
    repeat_exact_selection: bool = False
    engines: tuple[SelectionStalenessEngine, ...] = ("native", "dbt")
    engine_overrides: dict[SelectionStalenessEngine, SelectionStalenessEngineOverride] = field(
        default_factory=dict
    )
    notes: str = ""


@dataclass(frozen=True)
class SelectionStalenessEngineE2ETestCase:
    description: str
    engine: SelectionStalenessEngine
    scenario: SelectionStalenessE2ETestCase
    expected_rows_after_repair: tuple[tuple[object, ...], ...]
