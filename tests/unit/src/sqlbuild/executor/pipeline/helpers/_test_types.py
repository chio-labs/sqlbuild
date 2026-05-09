"""Test case types for SQL test pipeline helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SqlTestFunctionPreflightTestCase:
    """One SQL test function preflight scenario."""

    description: str
    expected_outcome: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ScenarioTestPipelineTestCase:
    """One scenario test pipeline orchestration case."""

    description: str
    scenario_names: tuple[str, ...]
    planning_failure_name: str
    expected_statuses: tuple[str, ...]
    expected_started_names: tuple[str, ...]
    expected_completed_names: tuple[str, ...]
    expected_completed_plan_names: tuple[str | None, ...]
    expected_connection_events: tuple[str, ...]
    expected_error_fragment: str
