"""Test case types for model migration integration tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class MigrationOutcomeTestCase:
    description: str
    expected_decisions: tuple[str, ...]
    expected_events: tuple[tuple[str, str, str], ...] = ()
    expected_destination_ids: tuple[int, ...] = ()
    expected_output_fragment: str = ""
    expected_reason: str = ""


@dataclass(frozen=True)
class BackAndForthMigrationTestCase:
    description: str
    expected_day_decisions: tuple[tuple[str, ...], ...]
    expected_day_five_ids: tuple[int, ...]
    expected_final_ids: tuple[int, ...]
    expected_events: tuple[tuple[str, str, str], ...]


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
    install_failure: Callable[[pytest.MonkeyPatch], None]
    rerun_with_force: bool
    expected_first_exit_code: int
    expected_decision_after_failure: str
    expected_final_decisions: tuple[str, ...]


@dataclass(frozen=True)
class AutomaticMigrationTestCase:
    description: str
    expected_migrations: tuple[tuple[str | None, str, str, str], ...] = ()
    expected_events: tuple[tuple[str, str, str], ...] = ()
    expected_reason: str = ""
    expected_warning: str = ""


@dataclass(frozen=True)
class PlanAsTargetTestCase:
    description: str
    preview_target: str
    expected_exit_code: int
    expected_decisions: tuple[str, ...] = ()
    expected_fragment: str = ""


@dataclass(frozen=True)
class VirtualModeMigrationTestCase:
    description: str
    expected_exit_code: int
    expected_fragment: str


@dataclass(frozen=True)
class StagedReplaceTestCase:
    description: str
    install_failure: Callable[[pytest.MonkeyPatch], None]
    expected_first_exit_code: int
    expected_relations_after_failure: tuple[str, ...]
    expected_previous_ids_after_failure: tuple[tuple[int, ...], ...]
    expected_decision_after_failure: str
    expected_final_previous_ids: tuple[tuple[int, ...], ...]
    expected_final_abandoned_stages: int
    expected_final_events: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class StagedPlanOutputTestCase:
    description: str
    expected_transfer: str
    expected_promotion: str
    expected_storage_transition: str | None
    expected_text_fragment: str


@dataclass(frozen=True)
class MigrationArchiveExpiryTestCase:
    description: str
    expected_archives_before: int
    expected_relations_after: tuple[str, ...]


@dataclass(frozen=True)
class IdentityHandoverTestCase:
    description: str
    middle_materialization: str
    install_failure: Callable[..., None]
    failing_model: str
    expected_first_exit_code: int
    expected_first_view_reason: str
    expected_retry_totals_reason: str
    expected_totals_rows: int
    expected_marked_total: int
    expected_events: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class RenamedPlanTextTestCase:
    description: str
    expected_fragment: str
