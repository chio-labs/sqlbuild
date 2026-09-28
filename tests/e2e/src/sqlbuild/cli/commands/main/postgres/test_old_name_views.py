"""PostgreSQL e2e coverage for compatibility views at migrated models' old names."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresOldNameJanitorE2ETestCase,
    PostgresOldNameViewE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    build_ok,
    build_unique_schema_name,
    cleanup_postgres_schema,
    ensure_postgres_schema_ready,
    execute_postgres_sql,
    fetch_postgres_rows,
    load_raw_orders,
    old_name_model_sql,
    ordered_ids,
    replace_view,
    write_migration_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

_ORIGIN: str = "revenue"
_DESTINATION: str = "daily_revenue"
_FIVE: tuple[tuple[object, ...], ...] = ((1,), (2,), (3,), (4,), (5,))
_SIX: tuple[tuple[object, ...], ...] = (*_FIVE, (6,))


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresOldNameViewE2ETestCase(
            description=materialized,
            materialized=materialized,
            expected_old_name_kind="v",
            expected_ids_after_rebuild=_SIX,
            expected_warning_fragment="M115: views not managed by SQLBuild depend on",
            expected_external_ids=_FIVE,
        )
        for materialized in ("table", "incremental")
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_model_when_rebuilding_on_postgres_then_old_name_view_follows_it(
    tmp_path: Path,
    test_case: PostgresOldNameViewE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """Identity-bound compatibility views are released and re-created around every rebuild."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_old_names")
    raw_schema_name: str = f"{schema_name}_raw"
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    external: str = f"{raw_schema_name}.revenue_report"
    try:
        project_dir: Path = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={_ORIGIN: old_name_model_sql(materialized=test_case.materialized)},
        )
        _ = build_ok(project_dir)
        execute_postgres_sql(
            sql=f"CREATE VIEW {external} AS SELECT order_id FROM {schema_name}.{_ORIGIN}",
            config=postgres_e2e_config,
        )
        project_dir = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={
                _DESTINATION: old_name_model_sql(
                    materialized=test_case.materialized, migrate_from=_ORIGIN
                )
            },
        )
        migrated: subprocess.CompletedProcess[str] = build_ok(project_dir)
        execute_postgres_sql(
            sql=(
                f"INSERT INTO {raw_schema_name}.raw_orders VALUES (6, TIMESTAMP '2026-01-06', 106)"
            ),
            config=postgres_e2e_config,
        )
        _ = build_ok(project_dir)
        _ = build_ok(project_dir)
        old_name_kind: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                "SELECT relkind FROM pg_class JOIN pg_namespace ON pg_namespace.oid = "
                f"relnamespace WHERE nspname = '{schema_name}' AND relname = '{_ORIGIN}'"
            ),
            config=postgres_e2e_config,
        )
        old_name_ids: tuple[tuple[object, ...], ...] = ordered_ids(
            relation=f"{schema_name}.{_ORIGIN}", config=postgres_e2e_config
        )
        external_ids: tuple[tuple[object, ...], ...] = ordered_ids(
            relation=external, config=postgres_e2e_config
        )
    finally:
        execute_postgres_sql(sql=f"DROP VIEW IF EXISTS {external}", config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=raw_schema_name, config=postgres_e2e_config)

    assert old_name_kind == ((test_case.expected_old_name_kind,),)
    assert old_name_ids == test_case.expected_ids_after_rebuild
    assert test_case.expected_warning_fragment in migrated.stdout, migrated.stdout
    assert external in migrated.stdout, migrated.stdout
    assert external_ids == test_case.expected_external_ids


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresOldNameJanitorE2ETestCase(
            description="sqlbuild's own view is dropped early",
            replacement_sql="",
            expected_janitor_fragment="└── drop  now  (requested; would expire ",
            expected_old_name_kinds=(),
        ),
        PostgresOldNameJanitorE2ETestCase(
            description="another view at the old name is left alone",
            replacement_sql="SELECT 1 AS order_id",
            expected_janitor_fragment="└── record  dropped  (name now used by another relation)",
            expected_old_name_kinds=(("v",),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_old_name_when_dropping_early_then_only_sqlbuilds_view_is_dropped(
    tmp_path: Path,
    test_case: PostgresOldNameJanitorE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """Janitor compares the view's definition with SQLBuild's before dropping it."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_old_name_janitor")
    raw_schema_name: str = f"{schema_name}_raw"
    view: str = f"{schema_name}.{_ORIGIN}"
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    try:
        project_dir: Path = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={_ORIGIN: old_name_model_sql(materialized="table")},
        )
        _ = build_ok(project_dir)
        project_dir = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={_DESTINATION: old_name_model_sql(materialized="table", migrate_from=_ORIGIN)},
        )
        _ = build_ok(project_dir)
        replace_view(view=view, sql=test_case.replacement_sql, config=postgres_e2e_config)
        janitor: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve", "--drop-old-name-view", view),
            project_dir=project_dir,
        )
        kinds: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                "SELECT relation.relkind FROM pg_class AS relation JOIN pg_namespace AS "
                "namespace ON namespace.oid = relation.relnamespace WHERE namespace.nspname = "
                f"'{schema_name}' AND relation.relname = '{_ORIGIN}'"
            ),
            config=postgres_e2e_config,
        )
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=raw_schema_name, config=postgres_e2e_config)

    assert janitor.returncode == 0, janitor.stdout + janitor.stderr
    assert kinds == test_case.expected_old_name_kinds
    assert test_case.expected_janitor_fragment in janitor.stdout, janitor.stdout
