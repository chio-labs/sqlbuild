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
class ScenarioFailureHelpTestCase:
    """One scenario failure help resolution case."""

    description: str
    error: Exception
    expected_help: str | None


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


@dataclass(frozen=True)
class ScenarioLocalPipelineTestCase:
    """One local scenario load-only pipeline case."""

    description: str
    snapshot_state: str
    strict: bool
    load_error_message: str | None
    expected_local_status: str
    expected_status: str
    expected_retained: bool
    expected_duckdb_exists: bool
    expected_error_code: str | None


@dataclass(frozen=True)
class SeedPipelineConcurrencyTestCase:
    """One seed pipeline concurrency orchestration case."""

    description: str
    seed_names: tuple[str, ...]
    max_concurrency: int
    expected_connection_count: int
    expected_seed_order: tuple[str, ...]
    expected_json_asset_order: tuple[str, ...]
