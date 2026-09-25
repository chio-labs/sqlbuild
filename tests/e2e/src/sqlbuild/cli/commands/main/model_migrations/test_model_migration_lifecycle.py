"""CLI e2e coverage for a model renamed away and back through staged migrations."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    MigrationLifecycleE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    build,
    load_raw_orders,
    migration_events,
    order_ids,
    plan_decisions,
    previous_archive_ids,
    write_orders_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationLifecycleE2ETestCase(
            description="rename away then back keeps history and archives the stale original",
            expected_step_decisions=("migrate", "superseded_replace", "done"),
            expected_final_ids=(1, 2, 3, 4, 5),
            expected_previous_archive_ids=((1, 2, 3),),
            expected_events=(
                ("stg_orders", "stg_customer_orders", "migrate"),
                ("stg_customer_orders", "stg_orders", "superseded_replace"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_renamed_away_and_back_when_building_then_history_follows_the_model(
    tmp_path: Path, test_case: MigrationLifecycleE2ETestCase
) -> None:
    """The real CLI stages, promotes, archives, and records each move."""

    project_dir: Path = write_orders_project(tmp_path=tmp_path, name="stg_orders", migrate_from="")
    load_raw_orders(project_dir=project_dir, last_day=3)
    initial: subprocess.CompletedProcess[str] = build(project_dir=project_dir)
    _ = write_orders_project(
        tmp_path=tmp_path, name="stg_customer_orders", migrate_from="stg_orders"
    )
    load_raw_orders(project_dir=project_dir, last_day=4)
    away_decisions: tuple[str, ...] = plan_decisions(project_dir=project_dir)
    away: subprocess.CompletedProcess[str] = build(project_dir=project_dir)
    _ = write_orders_project(
        tmp_path=tmp_path, name="stg_orders", migrate_from="stg_customer_orders"
    )
    load_raw_orders(project_dir=project_dir, last_day=5)
    back_decisions: tuple[str, ...] = plan_decisions(project_dir=project_dir)
    back: subprocess.CompletedProcess[str] = build(project_dir=project_dir)
    done_decisions: tuple[str, ...] = plan_decisions(project_dir=project_dir)

    assert initial.returncode == 0, initial.stdout + initial.stderr
    assert away.returncode == 0, away.stdout + away.stderr
    assert back.returncode == 0, back.stdout + back.stderr
    assert away_decisions + back_decisions + done_decisions == test_case.expected_step_decisions
    assert order_ids(project_dir=project_dir, relation="main.stg_orders") == (
        test_case.expected_final_ids
    )
    assert previous_archive_ids(project_dir=project_dir) == (
        test_case.expected_previous_archive_ids
    )
    assert migration_events(project_dir=project_dir) == test_case.expected_events


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
