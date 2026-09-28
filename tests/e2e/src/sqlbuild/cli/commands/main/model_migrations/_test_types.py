"""Test case types for model migration CLI e2e tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationLifecycleE2ETestCase:
    description: str
    expected_step_decisions: tuple[str, ...]
    expected_final_ids: tuple[int, ...]
    expected_previous_archive_ids: tuple[tuple[int, ...], ...]
    expected_events: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class ColumnMigrationLifecycleE2ETestCase:
    description: str
    expected_automatic_plan: str
    expected_retry_decisions: tuple[str, ...]
    expected_revenue: tuple[tuple[int, int], ...]
    expected_declared_notice: str
    expected_near_match_hint: str
    expected_final_columns: tuple[str, ...]
    expected_events: tuple[tuple[str, str, str, str], ...]


@dataclass(frozen=True)
class OldNameViewMaterializationE2ETestCase:
    description: str
    materialized: str
    expected_old_name_type: str
    expected_facts: tuple[str, ...]
    expected_rows: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class OldNameViewAliasE2ETestCase:
    description: str
    materialized: str
    origin_columns: str
    destination_columns: str
    destination_schema: str
    expected_old_columns: tuple[str, ...]
    expected_aliases: dict[str, str]


@dataclass(frozen=True)
class OldNameViewConfigE2ETestCase:
    description: str
    project_toml_extra: str
    extra_config: str
    expected_old_name_type: str
    expected_facts: tuple[str, ...]
    expected_retention: tuple[str | None, ...]
    expected_plan_fragment: str


@dataclass(frozen=True)
class OldNameViewJanitorE2ETestCase:
    description: str
    extra_config: str
    janitor_args: tuple[str, ...]
    wait_seconds: float
    expected_janitor_fragment: str
    expected_old_name_type: str | None
    expected_drop_reasons: tuple[str, ...]


@dataclass(frozen=True)
class OldNameClaimE2ETestCase:
    description: str
    expected_error_fragments: tuple[str, ...]


@dataclass(frozen=True)
class OldNameReferenceE2ETestCase:
    description: str
    header: str
    command: str
    expected_fragment: str


@dataclass(frozen=True)
class OldNameGatingE2ETestCase:
    description: str
    expected_old_name_type: str
    expected_facts: tuple[str, ...]


@dataclass(frozen=True)
class OldNameUnknownDropE2ETestCase:
    description: str
    requested_name: str
    expected_code: str
