from collections.abc import Callable
from dataclasses import dataclass, field

import pytest


@dataclass(frozen=True)
class PostgresBuildE2ETestCase:
    description: str
    expected_row_count: int
    expected_table_name: str = "fact_orders"
    command: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresPartialSourceTypeEnforcementE2ETestCase:
    description: str
    expected_rows: tuple[tuple[object, ...], ...]
    command: tuple[str, ...] = ("--no-color", "build", "--select", "stg_orders")
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresDbtProfileE2ETestCase:
    description: str
    expected_toml_fragments: tuple[str, ...]
    unexpected_toml_fragments: tuple[str, ...]
    expected_initial_rows: tuple[tuple[object, ...], ...]
    expected_changed_rows: tuple[tuple[object, ...], ...]
    expected_rerun_fragments: tuple[str, ...]
    expected_plain_selector_block_fragments: tuple[str, ...]
    expected_return_code: int = 0


@dataclass(frozen=True)
class PostgresDbtSeedChangeE2ETestCase:
    description: str
    expected_initial_total: int
    expected_changed_total: int
    expected_changed_fragments: tuple[str, ...]
    expected_rerun_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PostgresModelMigrationE2ETestCase:
    description: str
    expected_destination_ids: tuple[tuple[object, ...], ...]
    expected_view_ids: tuple[tuple[object, ...], ...]
    expected_archive_ids: tuple[tuple[object, ...], ...]
    expected_view_options: tuple[tuple[object, ...], ...]
    expected_events: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresMigrationRollbackE2ETestCase:
    description: str
    expected_failure_fragment: str
    expected_destination_ids_after_failure: tuple[tuple[object, ...], ...]
    expected_previous_archives_after_failure: int
    expected_final_destination_ids: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresColumnMigrationE2ETestCase:
    description: str
    expected_columns: tuple[tuple[object, ...], ...]
    expected_amounts: tuple[tuple[object, ...], ...]
    expected_view_amounts: tuple[tuple[object, ...], ...]
    expected_events: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresColumnMigrationRollbackE2ETestCase:
    description: str
    expected_failure_fragment: str
    expected_columns_after_failure: tuple[tuple[object, ...], ...]
    expected_final_columns: tuple[tuple[object, ...], ...]
    expected_events: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresOldNameViewE2ETestCase:
    description: str
    materialized: str
    expected_old_name_kind: str
    expected_ids_after_rebuild: tuple[tuple[object, ...], ...]
    expected_warning_fragment: str
    expected_external_ids: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresBoundViewCrashE2ETestCase:
    description: str
    materialized: str
    changed_columns: str
    install_failure: Callable[[pytest.MonkeyPatch], None]
    expected_crash_exit_code: int
    expected_view_ids_after_crash: tuple[tuple[object, ...], ...]
    expected_view_ids_after_retry: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresOldNameGrantsE2ETestCase:
    description: str
    reader_role: str
    expected_reader_ids: tuple[tuple[object, ...], ...]
    expected_grants: tuple[str, ...]
    expected_new_table_error: str
    expected_plan_fragment: str


@dataclass(frozen=True)
class PostgresOldNameRevokeE2ETestCase:
    description: str
    materialized: str
    rebuilt_columns: str
    revoked_role: str
    granted_role: str
    expected_revoked_error: str
    expected_granted_ids: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresOldNameJanitorE2ETestCase:
    description: str
    replacement_sql: str
    expected_janitor_fragment: str
    expected_old_name_kinds: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class PostgresDefaultPrivilegesE2ETestCase:
    description: str
    materialized: str
    rebuilt_columns: str
    role: str
    revoke_before_rebuild: bool
    expected_error: str


@dataclass(frozen=True)
class PostgresLongModelNameE2ETestCase:
    description: str
    model_name: str
    model_columns: str
    expected_exit_code: int
    expected_scenario_fragments: tuple[str, ...]
