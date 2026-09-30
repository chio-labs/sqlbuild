"""CLI e2e coverage for the janitor keeping the origin of a pending model migration."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.refactor._test_types import (
    PendingOriginJanitorE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.refactor.helpers import (
    load_raw_orders,
    order_history_files,
    order_ids,
    relation_type,
    sqb,
    write_orders_project,
)

_PENDING_REASON: str = "analytics.order_history  pending migration origin for order_ledger"


@pytest.mark.parametrize(
    "test_case",
    [
        PendingOriginJanitorE2ETestCase(
            description="janitor keeps the origin until the rename is migrated",
            janitor_args=("janitor", "--retention-days", "0", "--auto-approve"),
            expected_order_ids=(1, 2, 3, 4),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_pending_rename_when_janitor_runs_then_origin_survives_until_migrated(
    tmp_path: Path, test_case: PendingOriginJanitorE2ETestCase
) -> None:
    project_dir: Path = write_orders_project(
        tmp_path=tmp_path, files=order_history_files(materialized="incremental", udf=False)
    )
    first: subprocess.CompletedProcess[str] = sqb(project_dir, "build")
    renamed: subprocess.CompletedProcess[str] = sqb(
        project_dir, "rename", "model:order_history", "order_ledger"
    )

    pending: subprocess.CompletedProcess[str] = sqb(project_dir, *test_case.janitor_args)
    origin_after_pending: str | None = relation_type(project_dir=project_dir, name="order_history")
    load_raw_orders(project_dir=project_dir, order_ids=(3, 4))
    built: subprocess.CompletedProcess[str] = sqb(project_dir, "build")
    migrated: tuple[int, ...] = order_ids(project_dir=project_dir, name="order_ledger")
    settled: subprocess.CompletedProcess[str] = sqb(project_dir, *test_case.janitor_args)
    old_name_after_settled: str | None = relation_type(
        project_dir=project_dir, name="order_history"
    )
    dropped: subprocess.CompletedProcess[str] = sqb(
        project_dir, *test_case.janitor_args, "--drop-old-name-view", "order_history"
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert renamed.returncode == 0, renamed.stdout + renamed.stderr
    assert pending.returncode == 0, pending.stdout + pending.stderr
    assert _PENDING_REASON in pending.stdout
    assert origin_after_pending == "BASE TABLE"
    assert built.returncode == 0, built.stdout + built.stderr
    assert migrated == test_case.expected_order_ids
    assert settled.returncode == 0, settled.stdout + settled.stderr
    assert "pending migration origin" not in settled.stdout
    assert "analytics.order_history  -> model:order_ledger" in settled.stdout
    assert old_name_after_settled == "VIEW"
    assert dropped.returncode == 0, dropped.stdout + dropped.stderr
    assert relation_type(project_dir=project_dir, name="order_history") is None
