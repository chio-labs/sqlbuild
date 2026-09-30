"""CLI e2e coverage for `sqb rename model:` and `sqb mv` on a real DuckDB project."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.refactor._test_types import (
    DryRunE2ETestCase,
    ModelMigrationE2ETestCase,
    ModelRefactorE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.refactor.helpers import (
    fragments_present,
    load_raw_orders,
    order_history_files,
    order_ids,
    project_text,
    relation_type,
    sqb,
    sqb_json,
    write_orders_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ModelRefactorE2ETestCase(
            description="rename keeps the folder and rewrites refs and fixtures",
            command=("rename", "model:stg_orders", "stg_order_lines"),
            expected_removed="models/staging/stg_orders.sql",
            expected_file="models/staging/stg_order_lines.sql",
            expected_fragments={
                "models/marts/fact_orders.sql": ('__ref("stg_order_lines")',),
                "tests/unit/test_fact_orders.sql": ("__ref__stg_order_lines AS (",),
            },
            expected_relation="stg_order_lines",
        ),
        ModelRefactorE2ETestCase(
            description="rename rewrites cursor_inputs keys of incremental consumers",
            command=("rename", "model:stg_orders", "stg_order_lines"),
            expected_removed="models/staging/stg_orders.sql",
            expected_file="models/staging/stg_order_lines.sql",
            expected_fragments={
                "models/marts/order_history.sql": (
                    "stg_order_lines order_date,",
                    '__ref("stg_order_lines")',
                ),
            },
            expected_relation="order_history",
            extra_files=order_history_files(materialized="incremental", udf=False),
        ),
        ModelRefactorE2ETestCase(
            description="move to a new file renames the model after the file",
            command=("mv", "model:fact_orders", "models/reporting/order_facts.sql"),
            expected_removed="models/marts/fact_orders.sql",
            expected_file="models/reporting/order_facts.sql",
            expected_fragments={
                "models/marts/customer_totals.sql": ('__ref("order_facts")',),
                "tests/unit/test_fact_orders.sql": ("__expected__order_facts AS (",),
            },
            expected_relation="order_facts",
        ),
        ModelRefactorE2ETestCase(
            description="move into a folder keeps the model name",
            command=("mv", "model:customer_totals", "models/reporting/"),
            expected_removed="models/marts/customer_totals.sql",
            expected_file="models/reporting/customer_totals.sql",
            expected_fragments={},
            expected_relation="customer_totals",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_refactor_when_applied_then_project_tests_and_builds(
    tmp_path: Path, test_case: ModelRefactorE2ETestCase
) -> None:
    """Every reference and fixture follows the model, and the edited project really runs."""

    project_dir: Path = write_orders_project(tmp_path=tmp_path, files=test_case.extra_files)

    result: subprocess.CompletedProcess[str] = sqb(project_dir, *test_case.command)
    tested: subprocess.CompletedProcess[str] = sqb(project_dir, "test")
    built: subprocess.CompletedProcess[str] = sqb(project_dir, "build")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Compiled: ok" in result.stdout
    assert not (project_dir / test_case.expected_removed).exists()
    assert (project_dir / test_case.expected_file).is_file()
    files: dict[str, str] = project_text(project_dir)
    assert fragments_present(files=files, expected=test_case.expected_fragments), files
    assert tested.returncode == 0, tested.stdout + tested.stderr
    assert built.returncode == 0, built.stdout + built.stderr
    assert relation_type(project_dir=project_dir, name=test_case.expected_relation) is not None


@pytest.mark.parametrize(
    "test_case",
    [
        DryRunE2ETestCase(
            description="model rename",
            command=("rename", "model:stg_orders", "stg_order_lines", "--dry-run"),
            expected_paths=frozenset(
                {
                    "models/staging/stg_order_lines.sql",
                    "models/marts/fact_orders.sql",
                    "tests/unit/test_fact_orders.sql",
                }
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dry_run_json_when_refactoring_then_nothing_is_written(
    tmp_path: Path, test_case: DryRunE2ETestCase
) -> None:
    """A verified dry run reports its edits as JSON on stdout and progress on stderr."""

    project_dir: Path = write_orders_project(tmp_path=tmp_path)
    before: dict[str, str] = project_text(project_dir)

    result: subprocess.CompletedProcess[str] = sqb(project_dir, *test_case.command, "--json")
    code: int
    payload: dict[str, Any]
    code, payload = sqb_json(project_dir, *test_case.command)

    assert result.returncode == 0, result.stderr
    assert "Compiling project" in result.stderr
    assert code == 0
    assert payload["status"] == "dry_run"
    assert payload["files_changed"] == 0
    assert payload["compile"]["ok"] is True
    assert {item["path"] for item in payload["files"]} == test_case.expected_paths
    assert project_text(project_dir) == before


@pytest.mark.parametrize(
    "test_case",
    [
        ModelMigrationE2ETestCase(
            description="unfingerprintable table gains migrate_from",
            materialized="table",
            udf=True,
            expected_declaration="migrate_from order_history",
            expected_migrate_from_count=1,
            expected_old_name_type="VIEW",
            expected_order_ids=(3, 4),
        ),
        ModelMigrationE2ETestCase(
            description="unfingerprintable view gains migrate_from",
            materialized="view",
            udf=True,
            expected_declaration="migrate_from order_history",
            expected_migrate_from_count=1,
            expected_old_name_type="VIEW",
            expected_order_ids=(3, 4),
        ),
        ModelMigrationE2ETestCase(
            description="unfingerprintable incremental keeps its history",
            materialized="incremental",
            udf=True,
            expected_declaration="migrate_from order_history",
            expected_migrate_from_count=1,
            expected_old_name_type="VIEW",
            expected_order_ids=(1, 2, 3, 4),
        ),
        ModelMigrationE2ETestCase(
            description="unchanged definition is left to automatic discovery",
            materialized="incremental",
            udf=False,
            expected_declaration="",
            expected_migrate_from_count=0,
            expected_old_name_type="VIEW",
            expected_order_ids=(1, 2, 3, 4),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_built_model_when_renamed_then_build_migrates_its_relation(
    tmp_path: Path, test_case: ModelMigrationE2ETestCase
) -> None:
    """The rename declares migrate_from exactly when discovery would miss the old relation."""

    project_dir: Path = write_orders_project(
        tmp_path=tmp_path,
        files=order_history_files(materialized=test_case.materialized, udf=test_case.udf),
    )
    first: subprocess.CompletedProcess[str] = sqb(project_dir, "build")

    result: subprocess.CompletedProcess[str] = sqb(
        project_dir, "rename", "model:order_history", "order_ledger"
    )
    header: str = (project_dir / "models/marts/order_ledger.sql").read_text(encoding="utf-8")
    load_raw_orders(project_dir=project_dir, order_ids=(3, 4))
    second: subprocess.CompletedProcess[str] = sqb(project_dir, "build")

    assert first.returncode == 0, first.stdout + first.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert test_case.expected_declaration in header
    assert header.count("migrate_from") == test_case.expected_migrate_from_count, header
    assert second.returncode == 0, second.stdout + second.stderr
    assert relation_type(project_dir=project_dir, name="order_history") == (
        test_case.expected_old_name_type
    )
    assert order_ids(project_dir=project_dir, name="order_ledger") == test_case.expected_order_ids
