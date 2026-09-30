"""CLI e2e coverage for `sqb rename column:` and for refactorings that must not write."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.refactor._test_types import (
    ColumnMigrationE2ETestCase,
    ColumnRenameE2ETestCase,
    RefusedRefactorE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.refactor.helpers import (
    CENTS_MACRO,
    ORDER_EXPORT,
    fragments_present,
    load_raw_orders,
    order_history_files,
    order_ids,
    project_text,
    relation_columns,
    sqb,
    sqb_json,
    write_orders_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnRenameE2ETestCase(
            description="one step keeps downstream output names",
            command=("rename", "column:stg_orders.amount", "revenue"),
            expected_fragments={
                "models/staging/stg_orders.sql": ("  amount AS revenue,",),
                "models/marts/fact_orders.sql": ("  o.revenue AS amount,",),
                "tests/unit/test_fact_orders.sql": ("25 AS revenue",),
            },
            expected_columns={
                "stg_orders": ("order_id", "customer_id", "revenue", "order_date"),
                "fact_orders": ("order_id", "customer_id", "amount", "order_date"),
            },
        ),
        ColumnRenameE2ETestCase(
            description="cascade renames pass-through outputs downstream",
            command=("rename", "column:stg_orders.amount", "revenue", "--cascade"),
            expected_fragments={
                "models/marts/fact_orders.sql": ("  o.revenue,",),
                "models/marts/customer_totals.sql": ("SUM(revenue) AS total_amount",),
            },
            expected_columns={
                "fact_orders": ("order_id", "customer_id", "revenue", "order_date"),
                "customer_totals": ("customer_id", "total_amount"),
            },
        ),
        ColumnRenameE2ETestCase(
            description="cascade follows SELECT star consumers",
            command=("rename", "column:fact_orders.amount", "revenue", "--cascade"),
            extra_files=ORDER_EXPORT,
            expected_fragments={"models/marts/customer_totals.sql": ("SUM(revenue)",)},
            expected_columns={
                "fact_orders": ("order_id", "customer_id", "revenue", "order_date"),
                "order_export": ("order_id", "customer_id", "revenue", "order_date"),
            },
        ),
        ColumnRenameE2ETestCase(
            description="allow manual applies safe edits and lists the rest",
            command=("rename", "column:fact_orders.amount", "revenue", "--allow-manual"),
            extra_files=ORDER_EXPORT,
            expected_fragments={"models/marts/fact_orders.sql": ("  o.amount AS revenue,",)},
            expected_columns={
                "order_export": ("order_id", "customer_id", "revenue", "order_date"),
            },
            expected_manual=("models/marts/order_export.sql",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_column_rename_when_applied_then_project_tests_and_builds(
    tmp_path: Path, test_case: ColumnRenameE2ETestCase
) -> None:
    """Column references, fixtures, and outputs change together, and the project still runs."""

    project_dir: Path = write_orders_project(tmp_path=tmp_path, files=test_case.extra_files)

    code: int
    payload: dict[str, Any]
    code, payload = sqb_json(project_dir, *test_case.command)
    tested: subprocess.CompletedProcess[str] = sqb(project_dir, "test")
    built: subprocess.CompletedProcess[str] = sqb(project_dir, "build")

    assert code == 0, payload
    assert payload["status"] == "applied"
    assert tuple(item["path"] for item in payload["manual"]) == test_case.expected_manual
    files: dict[str, str] = project_text(project_dir)
    assert fragments_present(files=files, expected=test_case.expected_fragments), files
    assert tested.returncode == 0, tested.stdout + tested.stderr
    assert built.returncode == 0, built.stdout + built.stderr
    assert {
        name: relation_columns(project_dir=project_dir, name=name)
        for name in test_case.expected_columns
    } == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        RefusedRefactorE2ETestCase(
            description="move out of a macro scope",
            command=("mv", "model:stg_order_cents", "models/marts/"),
            extra_files=CENTS_MACRO,
            expected_status="refused",
            expected_reason="macro:to_cents used by model:stg_order_cents is not visible",
        ),
        RefusedRefactorE2ETestCase(
            description="rename onto an existing model",
            command=("rename", "model:stg_orders", "fact_orders"),
            extra_files={},
            expected_status="refused",
            expected_reason="model:fact_orders already exists",
        ),
        RefusedRefactorE2ETestCase(
            description="column used inside macro-generated SQL",
            command=("rename", "column:stg_orders.amount", "revenue"),
            extra_files=CENTS_MACRO,
            expected_status="refused",
            expected_reason="referenced in SQL a macro generates",
        ),
        RefusedRefactorE2ETestCase(
            description="SELECT star consumer without cascade",
            command=("rename", "column:fact_orders.amount", "revenue"),
            extra_files=ORDER_EXPORT,
            expected_status="refused",
            expected_reason="rerun with --cascade",
        ),
        RefusedRefactorE2ETestCase(
            description="allow manual that leaves the project broken",
            command=("rename", "column:stg_orders.amount", "revenue", "--allow-manual"),
            extra_files=CENTS_MACRO,
            expected_status="compile_failed",
            expected_reason="Unknown column 'amount'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_refactor_when_running_then_no_file_changes(
    tmp_path: Path, test_case: RefusedRefactorE2ETestCase
) -> None:
    """Refusals and failed verification exit 1, explain why, and leave every file untouched."""

    project_dir: Path = write_orders_project(tmp_path=tmp_path, files=test_case.extra_files)
    before: dict[str, str] = project_text(project_dir)

    code: int
    payload: dict[str, Any]
    code, payload = sqb_json(project_dir, *test_case.command)
    text: subprocess.CompletedProcess[str] = sqb(project_dir, *test_case.command)

    assert code == 1
    assert payload["status"] == test_case.expected_status
    assert test_case.expected_reason in json.dumps(payload)
    assert text.returncode == 1
    assert "no files changed" in text.stdout
    assert project_text(project_dir) == before


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnMigrationE2ETestCase(
            description="incremental column renamed in place",
            expected_declaration="revenue (migrate_from amount)",
            expected_columns=("order_id", "revenue", "order_date"),
            expected_order_ids=(1, 2, 3, 4),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_built_incremental_when_renaming_column_then_build_keeps_history(
    tmp_path: Path, test_case: ColumnMigrationE2ETestCase
) -> None:
    """The rename declares the column migration, so the next build renames it in place."""

    project_dir: Path = write_orders_project(
        tmp_path=tmp_path, files=order_history_files(materialized="incremental", udf=False)
    )
    first: subprocess.CompletedProcess[str] = sqb(project_dir, "build")

    result: subprocess.CompletedProcess[str] = sqb(
        project_dir, "rename", "column:order_history.amount", "revenue"
    )
    header: str = (project_dir / "models/marts/order_history.sql").read_text(encoding="utf-8")
    load_raw_orders(project_dir=project_dir, order_ids=(3, 4))
    second: subprocess.CompletedProcess[str] = sqb(project_dir, "build")

    assert first.returncode == 0, first.stdout + first.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert test_case.expected_declaration in header, header
    assert second.returncode == 0, second.stdout + second.stderr
    assert relation_columns(project_dir=project_dir, name="order_history") == (
        test_case.expected_columns
    )
    assert order_ids(project_dir=project_dir, name="order_history") == (
        test_case.expected_order_ids
    )
