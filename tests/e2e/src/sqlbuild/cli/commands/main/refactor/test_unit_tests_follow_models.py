"""CLI e2e coverage: a model's unit tests follow it through `sqb rename` and `sqb mv`."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.refactor._test_types import (
    FollowedUnitTestDryRunE2ETestCase,
    FollowedUnitTestE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.refactor.helpers import (
    FACT_ORDERS_TEST,
    fragments_present,
    project_text,
    project_toml,
    remove_files,
    sqb,
    sqb_json,
    write_orders_project,
)

_MIRRORED_TEST: str = "tests/unit/marts/test_fact_orders__keeps_orders.sql"
_SHARED_TEST: str = "tests/unit/marts/test_marts__totals_follow_orders.sql"
_TEST_RULES: str = '\n[rules]\nselect = ["SQBRTEST102", "SQBRTEST103", "SQBRTEST104"]\n'
_CUSTOMER_TOTALS_FIXTURE: str = (
    "__expected__customer_totals AS (\n  SELECT 10 AS customer_id, 25 AS total_amount\n)\n"
)
_FILES: dict[str, str] = {
    "sqlbuild_project.toml": project_toml() + _TEST_RULES,
    _MIRRORED_TEST: FACT_ORDERS_TEST.replace("TEST();", 'TEST (name "fact_orders__keeps_orders");'),
}
_SHARED_FILES: dict[str, str] = {
    _SHARED_TEST: FACT_ORDERS_TEST.replace(
        "TEST();", 'TEST (name "marts__totals_follow_orders");'
    ).replace(")\nSELECT 1\n", f"),\n{_CUSTOMER_TOTALS_FIXTURE}SELECT 1\n"),
}


@pytest.mark.parametrize(
    "test_case",
    [
        FollowedUnitTestE2ETestCase(
            description="rename renames the test file and its TEST name",
            command=("rename", "model:fact_orders", "order_facts"),
            expected_fragments={
                "tests/unit/marts/test_order_facts__keeps_orders.sql": (
                    'TEST (name "order_facts__keeps_orders");',
                    "__expected__order_facts",
                ),
                _SHARED_TEST: (
                    'TEST (name "marts__totals_follow_orders");',
                    "__expected__order_facts AS (",
                ),
            },
            extra_files=_SHARED_FILES,
        ),
        FollowedUnitTestE2ETestCase(
            description="move to another folder moves the test to the mirrored folder",
            command=("mv", "model:fact_orders", "models/reporting/"),
            expected_fragments={
                "tests/unit/reporting/test_fact_orders__keeps_orders.sql": (
                    'TEST (name "fact_orders__keeps_orders");',
                    "__expected__fact_orders",
                ),
            },
        ),
        FollowedUnitTestE2ETestCase(
            description="move with a new name moves and renames the test",
            command=("mv", "model:fact_orders", "models/reporting/order_facts.sql"),
            expected_fragments={
                "tests/unit/reporting/test_order_facts__keeps_orders.sql": (
                    'TEST (name "order_facts__keeps_orders");',
                    "__expected__order_facts",
                ),
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_with_unit_test_when_refactored_then_test_follows_and_passes(
    tmp_path: Path, test_case: FollowedUnitTestE2ETestCase
) -> None:
    """The model's own test is renamed and moved with it; a shared test only has fixtures edited."""

    project_dir: Path = write_orders_project(
        tmp_path=tmp_path, files={**_FILES, **test_case.extra_files}
    )
    remove_files(project_dir=project_dir, paths=("tests/unit/test_fact_orders.sql",))

    result: subprocess.CompletedProcess[str] = sqb(project_dir, *test_case.command)
    tested: subprocess.CompletedProcess[str] = sqb(project_dir, "test")

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (project_dir / _MIRRORED_TEST).exists()
    files: dict[str, str] = project_text(project_dir)
    assert fragments_present(files=files, expected=test_case.expected_fragments), files
    assert tested.returncode == 0, tested.stdout + tested.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        FollowedUnitTestDryRunE2ETestCase(
            description="dry-run rename lists the renamed test file",
            command=("rename", "model:fact_orders", "order_facts", "--dry-run"),
            expected_status="dry_run",
            expected_path="tests/unit/marts/test_order_facts__keeps_orders.sql",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dry_run_when_renaming_model_with_unit_test_then_reports_move_and_writes_nothing(
    tmp_path: Path, test_case: FollowedUnitTestDryRunE2ETestCase
) -> None:
    """A dry run lists the test file at its new path and leaves every file untouched."""

    project_dir: Path = write_orders_project(tmp_path=tmp_path, files=_FILES)
    remove_files(project_dir=project_dir, paths=("tests/unit/test_fact_orders.sql",))
    before: dict[str, str] = project_text(project_dir)

    code: int
    payload: dict[str, Any]
    code, payload = sqb_json(project_dir, *test_case.command)

    assert code == 0, payload
    assert payload["status"] == test_case.expected_status
    assert test_case.expected_path in [str(item["path"]) for item in payload["files"]]
    assert project_text(project_dir) == before
