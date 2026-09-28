"""PostgreSQL e2e coverage for compatibility views keeping the old table's privileges."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresDefaultPrivilegesE2ETestCase,
    PostgresOldNameGrantsE2ETestCase,
    PostgresOldNameRevokeE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    build_ok,
    build_unique_schema_name,
    cleanup_postgres_schema,
    create_login_role,
    ensure_postgres_schema_ready,
    execute_postgres_sql,
    fetch_postgres_rows,
    load_raw_orders,
    old_name_model_sql,
    reader_error,
    reader_rows,
    revoke_view_select,
    write_migration_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

_FIVE: tuple[tuple[object, ...], ...] = ((1,), (2,), (3,), (4,), (5,))
_SIX: tuple[tuple[object, ...], ...] = (*_FIVE, (6,))


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresOldNameGrantsE2ETestCase(
            description="select-only reader of the old table",
            reader_role="orders_reader",
            expected_reader_ids=_SIX,
            expected_grants=('GRANT SELECT ON {view} TO "orders_reader"',),
            expected_new_table_error="permission denied for table daily_revenue",
            expected_plan_fragment="        ├── grants  1 copied from the old table\n",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reader_of_old_table_when_model_is_renamed_then_reader_keeps_access_through_view(
    tmp_path: Path,
    test_case: PostgresOldNameGrantsE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """The view copies the archived table's privileges and grants nothing new."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_old_name_grants")
    raw_schema_name: str = f"{schema_name}_raw"
    role: str = test_case.reader_role
    view: str = f"{schema_name}.revenue"
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    execute_postgres_sql(
        sql=(
            f"DO $$ BEGIN CREATE ROLE {role} LOGIN PASSWORD '{role}'; "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        ),
        config=postgres_e2e_config,
    )
    try:
        project_dir: Path = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={"revenue": old_name_model_sql(materialized="table")},
        )
        _ = build_ok(project_dir)
        execute_postgres_sql(
            sql=f"GRANT USAGE ON SCHEMA {schema_name} TO {role}", config=postgres_e2e_config
        )
        execute_postgres_sql(sql=f"GRANT SELECT ON {view} TO {role}", config=postgres_e2e_config)
        project_dir = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={
                "daily_revenue": old_name_model_sql(materialized="table", migrate_from="revenue")
            },
        )
        _ = build_ok(project_dir)
        execute_postgres_sql(
            sql=(
                f"INSERT INTO {raw_schema_name}.raw_orders VALUES (6, TIMESTAMP '2026-01-06', 106)"
            ),
            config=postgres_e2e_config,
        )
        _ = build_ok(project_dir)
        reader_ids: tuple[tuple[object, ...], ...] = reader_rows(
            config=postgres_e2e_config, role=role, sql=f"SELECT order_id FROM {view} ORDER BY 1"
        )
        new_table_error: str = reader_error(
            config=postgres_e2e_config,
            role=role,
            sql=f"SELECT order_id FROM {schema_name}.daily_revenue",
        )
        plan_text: str = run_sqb(command=("--no-color", "plan"), project_dir=project_dir).stdout
        plan_json: dict[str, Any] = json.loads(
            run_sqb(command=("--no-color", "plan", "--json"), project_dir=project_dir).stdout
        )
        recorded: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT grants_copied FROM {schema_name}._sqlbuild_old_name_views "
                "WHERE event_type = 'view_created'"
            ),
            config=postgres_e2e_config,
        )
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=raw_schema_name, config=postgres_e2e_config)

    assert test_case.expected_plan_fragment in plan_text, plan_text
    assert [entry["grants_copied"] for entry in plan_json["old_names"]] == [
        len(test_case.expected_grants)
    ]
    assert reader_ids == test_case.expected_reader_ids
    assert new_table_error == test_case.expected_new_table_error
    assert tuple(json.loads(str(recorded[0][0]))) == tuple(
        grant.format(view=view) for grant in test_case.expected_grants
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresOldNameRevokeE2ETestCase(
            description="table rebuild replaces the view in place",
            materialized="table",
            rebuilt_columns="order_id, order_date, amount_cents",
            revoked_role="orders_revoked_table",
            granted_role="orders_granted_table",
            expected_revoked_error="permission denied for view revenue",
            expected_granted_ids=_SIX,
        ),
        PostgresOldNameRevokeE2ETestCase(
            description="dropped column re-creates the view with its current privileges",
            materialized="incremental_sync",
            rebuilt_columns="order_id, order_date",
            revoked_role="orders_revoked_sync",
            granted_role="orders_granted_sync",
            expected_revoked_error="permission denied for view revenue",
            expected_granted_ids=_SIX,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_view_privileges_changed_when_destination_rebuilds_then_current_privileges_stay(
    tmp_path: Path,
    test_case: PostgresOldNameRevokeE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """A rebuild never restores a revoked privilege and never loses one granted on the view."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_old_name_revoke")
    raw_schema_name: str = f"{schema_name}_raw"
    view: str = f"{schema_name}.revenue"
    revoked: str = test_case.revoked_role
    granted: str = test_case.granted_role
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    create_login_role(role=revoked, config=postgres_e2e_config)
    create_login_role(role=granted, config=postgres_e2e_config)
    try:
        project_dir: Path = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={"revenue": old_name_model_sql(materialized=test_case.materialized)},
        )
        _ = build_ok(project_dir)
        execute_postgres_sql(
            sql=f"GRANT USAGE ON SCHEMA {schema_name} TO {revoked}, {granted}",
            config=postgres_e2e_config,
        )
        execute_postgres_sql(sql=f"GRANT SELECT ON {view} TO {revoked}", config=postgres_e2e_config)
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
        _ = build_ok(project_dir)
        execute_postgres_sql(
            sql=f"REVOKE SELECT ON {view} FROM {revoked}", config=postgres_e2e_config
        )
        execute_postgres_sql(sql=f"GRANT SELECT ON {view} TO {granted}", config=postgres_e2e_config)
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
                    columns=test_case.rebuilt_columns,
                )
            },
        )
        _ = build_ok(project_dir)
        revoked_error: str = reader_error(
            config=postgres_e2e_config, role=revoked, sql=f"SELECT order_id FROM {view}"
        )
        granted_ids: tuple[tuple[object, ...], ...] = reader_rows(
            config=postgres_e2e_config,
            role=granted,
            sql=f"SELECT order_id FROM {view} ORDER BY 1",
        )
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=raw_schema_name, config=postgres_e2e_config)

    assert revoked_error == test_case.expected_revoked_error
    assert granted_ids == test_case.expected_granted_ids


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresDefaultPrivilegesE2ETestCase(
            description="default privileges do not reach a new compatibility view",
            materialized="table",
            rebuilt_columns="order_id, order_date, amount_cents",
            role="orders_default_create",
            revoke_before_rebuild=False,
            expected_error="permission denied for view revenue",
        ),
        PostgresDefaultPrivilegesE2ETestCase(
            description="drop and re-create does not restore a revoked default privilege",
            materialized="incremental_sync",
            rebuilt_columns="order_id, order_date",
            role="orders_default_recreate",
            revoke_before_rebuild=True,
            expected_error="permission denied for view revenue",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_default_privileges_when_view_is_recreated_then_grants_match_before(
    tmp_path: Path,
    test_case: PostgresDefaultPrivilegesE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """Schema default privileges applied by a re-create are revoked again."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_old_name_defaults")
    raw_schema_name: str = f"{schema_name}_raw"
    view: str = f"{schema_name}.revenue"
    role: str = test_case.role
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    create_login_role(role=role, config=postgres_e2e_config)
    try:
        project_dir: Path = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={"revenue": old_name_model_sql(materialized=test_case.materialized)},
        )
        _ = build_ok(project_dir)
        execute_postgres_sql(
            sql=f"GRANT USAGE ON SCHEMA {schema_name} TO {role}", config=postgres_e2e_config
        )
        execute_postgres_sql(
            sql=(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT SELECT ON TABLES TO {role}"
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
                    materialized=test_case.materialized, migrate_from="revenue"
                )
            },
        )
        _ = build_ok(project_dir)
        revoke_view_select(
            view=view,
            role=role,
            revoke=test_case.revoke_before_rebuild,
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
                    columns=test_case.rebuilt_columns,
                )
            },
        )
        _ = build_ok(project_dir)
        error: str = reader_error(
            config=postgres_e2e_config, role=role, sql=f"SELECT order_id FROM {view}"
        )
    finally:
        execute_postgres_sql(
            sql=(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} "
                f"REVOKE SELECT ON TABLES FROM {role}"
            ),
            config=postgres_e2e_config,
        )
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=raw_schema_name, config=postgres_e2e_config)

    assert error == test_case.expected_error
