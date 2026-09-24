"""Integration coverage for inspection-only plan --as previews of migrations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    TARGETS_PROJECT_TOML,
    CliRun,
    incremental_orders_sql,
    load_raw_orders,
    plan_json,
    query,
    run_sqb,
    write_project,
)

_ORIGIN: str = "stg_orders"
_DESTINATION: str = "stg_customer_orders"


def _warehouse_state(*, project_dir: Path) -> list[tuple[Any, ...]]:
    tables: list[tuple[Any, ...]] = query(
        project_dir=project_dir,
        sql=(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('dev', 'prod') ORDER BY 1, 2"
        ),
    )
    counts: list[tuple[Any, ...]] = [
        (
            schema,
            name,
            query(project_dir=project_dir, sql=f"SELECT count(*) FROM {schema}.{name}")[0][0],
        )
        for schema, name in tables
    ]
    return counts


def _prepare_prod_rename(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_project(
        project_dir=project_dir,
        models={_ORIGIN: incremental_orders_sql()},
        project_toml=TARGETS_PROJECT_TOML,
    )
    load_raw_orders(project_dir=project_dir, first_day=1, last_day=4)
    built: CliRun = run_sqb(
        project_dir=project_dir, args=("build", "--target", "prod"), capsys=capsys
    )
    assert built.exit_code == 0, built.output
    write_project(
        project_dir=project_dir,
        models={_DESTINATION: incremental_orders_sql(migrate_from=_ORIGIN)},
        project_toml=TARGETS_PROJECT_TOML,
    )


def test_given_pending_prod_migration_when_planning_as_prod_then_previews_without_mutation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepare_prod_rename(project_dir=tmp_path, capsys=capsys)
    before: list[tuple[Any, ...]] = _warehouse_state(project_dir=tmp_path)

    preview: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys, args=("--as", "prod"))
    active: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    text: CliRun = run_sqb(project_dir=tmp_path, args=("plan", "--as", "prod"), capsys=capsys)
    after: list[tuple[Any, ...]] = _warehouse_state(project_dir=tmp_path)

    assert [migration["decision"] for migration in preview["migrations"]] == ["migrate"]
    assert preview["migrations"][0]["destination"] == "prod.stg_customer_orders"
    assert [migration["decision"] for migration in active["migrations"]] == ["origin_missing"]
    assert text.exit_code == 0, text.output
    assert "Previewing plan as target 'prod'" in text.output
    assert "migrate  prod.stg_orders -> prod.stg_customer_orders" in text.output
    assert after == before
    assert ("prod", "_sqlbuild_migrations", 0) not in after
    assert all(name != _DESTINATION for _, name, _ in after)


def test_given_executed_prod_migration_when_planning_as_prod_then_reports_done(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepare_prod_rename(project_dir=tmp_path, capsys=capsys)
    migrated: CliRun = run_sqb(
        project_dir=tmp_path, args=("build", "--target", "prod"), capsys=capsys
    )
    before: list[tuple[Any, ...]] = _warehouse_state(project_dir=tmp_path)

    preview: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys, args=("--as", "prod"))

    assert migrated.exit_code == 0, migrated.output
    assert [migration["decision"] for migration in preview["migrations"]] == ["done"]
    assert preview["migrations"][0]["target"] == "prod"
    assert _warehouse_state(project_dir=tmp_path) == before


def test_given_unknown_target_when_planning_as_it_then_fails_clearly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepare_prod_rename(project_dir=tmp_path, capsys=capsys)

    result: CliRun = run_sqb(project_dir=tmp_path, args=("plan", "--as", "staging"), capsys=capsys)

    assert result.exit_code == 1
    assert "unknown target 'staging' for plan --as" in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
