"""Test case types for model migration integration tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationCompileErrorTestCase:
    description: str
    model_sql: str
    expected_fragment: str


@dataclass(frozen=True)
class MigrationCompatibilityTestCase:
    description: str
    origin_setup_sql: str
    destination_extra_config: str
    destination_select_sql: str
    expected_compatibility: str
    expected_build_exit_code: int
    expected_fragment: str


@dataclass(frozen=True)
class MigrationInterruptionTestCase:
    description: str
    failure_point: str
    expected_first_exit_code: int
    expected_decision_after_failure: str
    rerun_with_force: bool
    expected_final_decisions: tuple[str, ...]
