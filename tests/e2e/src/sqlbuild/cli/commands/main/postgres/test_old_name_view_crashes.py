"""PostgreSQL fault injection proving compatibility views survive a crash at every promotion point."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresBoundViewCrashE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    build_in_process,
    build_unique_schema_name,
    cleanup_postgres_schema,
    ensure_postgres_schema_ready,
    execute_postgres_sql,
    fail_bound_view_rebind,
    fail_column_drop,
    fail_displaced_drop,
    fail_mid_swap,
    load_raw_orders,
    no_postgres_failure,
    old_name_model_sql,
    ordered_ids,
    write_migration_project,
)

_FIVE: tuple[tuple[object, ...], ...] = ((1,), (2,), (3,), (4,), (5,))
_SIX: tuple[tuple[object, ...], ...] = (*_FIVE, (6,))
_ALL_COLUMNS: str = "order_id, order_date, amount_cents"
_WITHOUT_AMOUNT: str = "order_id, order_date"


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresBoundViewCrashE2ETestCase(
            description="table rebuild crashing between swap renames",
            materialized="table",
            changed_columns=_ALL_COLUMNS,
            install_failure=fail_mid_swap,
            expected_crash_exit_code=1,
            expected_view_ids_after_crash=_FIVE,
            expected_view_ids_after_retry=_SIX,
        ),
        PostgresBoundViewCrashE2ETestCase(
            description="table rebuild crashing before views follow the new table",
            materialized="table",
            changed_columns=_ALL_COLUMNS,
            install_failure=fail_bound_view_rebind,
            expected_crash_exit_code=1,
            expected_view_ids_after_crash=_FIVE,
            expected_view_ids_after_retry=_SIX,
        ),
        PostgresBoundViewCrashE2ETestCase(
            description="table rebuild crashing before the displaced table is dropped",
            materialized="table",
            changed_columns=_ALL_COLUMNS,
            install_failure=fail_displaced_drop,
            expected_crash_exit_code=1,
            expected_view_ids_after_crash=_FIVE,
            expected_view_ids_after_retry=_SIX,
        ),
        PostgresBoundViewCrashE2ETestCase(
            description="table rebuild without a crash",
            materialized="table",
            changed_columns=_ALL_COLUMNS,
            install_failure=no_postgres_failure,
            expected_crash_exit_code=0,
            expected_view_ids_after_crash=_SIX,
            expected_view_ids_after_retry=_SIX,
        ),
        PostgresBoundViewCrashE2ETestCase(
            description="incremental column drop crashing after views are released",
            materialized="incremental_sync",
            changed_columns=_WITHOUT_AMOUNT,
            install_failure=fail_column_drop,
            expected_crash_exit_code=1,
            expected_view_ids_after_crash=_FIVE,
            expected_view_ids_after_retry=_SIX,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_compatibility_view_when_rebuild_crashes_then_view_is_never_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    test_case: PostgresBoundViewCrashE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """Views bound to the replaced relation change only inside the promoting transaction."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_old_name_crash")
    raw_schema_name: str = f"{schema_name}_raw"
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    view: str = f"{schema_name}.revenue"
    try:
        project_dir: Path = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={"revenue": old_name_model_sql(materialized=test_case.materialized)},
        )
        assert build_in_process(project_dir=project_dir, capsys=capsys) == 0
        project_dir = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={
                "daily_revenue": old_name_model_sql(
                    materialized=test_case.materialized, migrate_from="revenue"
                )
            },
        )
        assert build_in_process(project_dir=project_dir, capsys=capsys) == 0
        execute_postgres_sql(
            sql=(
                f"INSERT INTO {raw_schema_name}.raw_orders VALUES (6, TIMESTAMP '2026-01-06', 106)"
            ),
            config=postgres_e2e_config,
        )
        project_dir = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={
                "daily_revenue": old_name_model_sql(
                    materialized=test_case.materialized,
                    migrate_from="revenue",
                    columns=test_case.changed_columns,
                )
            },
        )
        with monkeypatch.context() as patch:
            test_case.install_failure(patch)
            crash_exit_code: int = build_in_process(project_dir=project_dir, capsys=capsys)
        after_crash: tuple[tuple[object, ...], ...] = ordered_ids(
            relation=view, config=postgres_e2e_config
        )
        assert build_in_process(project_dir=project_dir, capsys=capsys) == 0
        after_retry: tuple[tuple[object, ...], ...] = ordered_ids(
            relation=view, config=postgres_e2e_config
        )
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=raw_schema_name, config=postgres_e2e_config)

    assert crash_exit_code == test_case.expected_crash_exit_code
    assert after_crash == test_case.expected_view_ids_after_crash
    assert after_retry == test_case.expected_view_ids_after_retry
