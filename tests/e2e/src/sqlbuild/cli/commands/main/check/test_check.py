"""E2E tests for the sqb check command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.check._test_types import CheckCommandTestCase
from tests.e2e.src.sqlbuild.cli.commands.main.check.helpers import (
    assert_expected_file_fragments,
    initialize_state_when_requested,
    prepare_check_project_by_kind,
    resolve_check_command,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

TEST_CASES: tuple[CheckCommandTestCase, ...] = (
    CheckCommandTestCase(
        description="runs all checks with implicit dependencies",
        command=("--no-color", "check"),
        expected_returncode=1,
        expected_stdout_fragments=(
            "Execution  sqb check",
            "Python checks",
            "check_orders_export",
            "warn_orders_export",
            "WARN",
            "fail_orders_export",
            "FAIL",
            "false_orders_export",
            "exception_orders_export",
            "orders exception check failed",
            "PASS=3  WARN=1  FAIL=3  TOTAL=7",
        ),
    ),
    CheckCommandTestCase(
        description="runs expanded selected check",
        command=("--no-color", "check", "--select", "+check:check_orders_export"),
        expected_returncode=0,
        expected_stdout_fragments=(
            "Python checks",
            "check_orders_export",
            "PASS",
            "PASS=1  WARN=0  FAIL=0  TOTAL=1",
        ),
    ),
    CheckCommandTestCase(
        description="fails selected check with missing dependency",
        command=("--no-color", "check", "--select", "check:check_orders_export"),
        expected_returncode=1,
        expected_stdout_fragments=(
            "Python check 'check_orders_export' depends on unselected Python node 'export_orders'",
        ),
    ),
    CheckCommandTestCase(
        description="build executes relevant checks",
        command=("--no-color", "build", "--exclude", "tag:failure"),
        expected_returncode=0,
        expected_stdout_fragments=(
            "Python checks",
            "check_orders_export",
            "check_orders_asset",
            "check_order_customer_exports",
            "warn_orders_export",
            "WARN",
        ),
    ),
    CheckCommandTestCase(
        description="failing check fails build",
        command=("--no-color", "build"),
        expected_returncode=1,
        expected_stdout_fragments=(
            "Python checks",
            "fail_orders_export",
            "FAIL",
            "orders export failed",
        ),
    ),
    CheckCommandTestCase(
        description="selected false check fails check command",
        command=("--no-color", "check", "--select", "+check:false_orders_export"),
        expected_returncode=1,
        expected_stdout_fragments=(
            "false_orders_export",
            "FAIL",
            "PASS=0  WARN=0  FAIL=1  TOTAL=1",
        ),
    ),
    CheckCommandTestCase(
        description="selected exception check fails check command",
        command=("--no-color", "check", "--select", "+check:exception_orders_export"),
        expected_returncode=1,
        expected_stdout_fragments=(
            "exception_orders_export",
            "orders exception check failed",
            "PASS=0  WARN=0  FAIL=1  TOTAL=1",
        ),
    ),
    CheckCommandTestCase(
        description="build json includes Python check results",
        command=("--no-color", "build", "--json", "--exclude", "tag:failure"),
        expected_returncode=0,
        expected_stdout_fragments=(
            '"kind": "python_check"',
            '"name": "check_orders_asset"',
            '"python_check_warn_count": 1',
        ),
    ),
    CheckCommandTestCase(
        description="build json marks failed Python checks",
        command=("--no-color", "build", "--json"),
        expected_returncode=1,
        expected_stdout_fragments=(
            '"status": "failed"',
            '"kind": "python_check"',
            '"name": "false_orders_export"',
            '"python_check_fail_count": 3',
        ),
    ),
    CheckCommandTestCase(
        description="tag selector runs multi-dependency check",
        command=("--no-color", "check", "--select", "+tag:multi"),
        expected_returncode=0,
        expected_stdout_fragments=(
            "check_order_customer_exports",
            "PASS=1  WARN=0  FAIL=0  TOTAL=1",
        ),
    ),
    CheckCommandTestCase(
        description="json output includes selected Python check",
        command=("--no-color", "check", "--json", "--select", "+tag:multi"),
        expected_returncode=0,
        expected_stdout_fragments=(
            '"checks"',
            '"name": "check_order_customer_exports"',
            '"status": "pass"',
            '"metadata": {',
        ),
    ),
    CheckCommandTestCase(
        description="json output path writes selected Python check",
        command=(
            "--no-color",
            "check",
            "--json-output",
            "{project_dir}/target/check.json",
            "--select",
            "+tag:multi",
        ),
        expected_returncode=0,
        expected_stdout_fragments=("PASS=1  WARN=0  FAIL=0  TOTAL=1",),
        expected_file_fragments=(
            (
                "target/check.json",
                (
                    '"command": "check"',
                    '"name": "check_order_customer_exports"',
                    '"check_id": "python_check:check_order_customer_exports"',
                ),
            ),
        ),
    ),
    CheckCommandTestCase(
        description="check command executes terminal loader check",
        command=("--no-color", "check"),
        expected_returncode=0,
        expected_stdout_fragments=(
            "check_raw_orders_loader",
            "PASS=1  WARN=0  FAIL=0  TOTAL=1",
        ),
        project_kind="terminal_loader",
    ),
    CheckCommandTestCase(
        description="virtual build executes relevant Python checks",
        command=("--no-color", "build"),
        expected_returncode=0,
        expected_stdout_fragments=(
            "Python checks",
            "check_virtual_orders",
            "PASS",
        ),
        project_kind="virtual",
        initialize_state=True,
    ),
    CheckCommandTestCase(
        description="virtual build fails on error Python check",
        command=("--no-color", "build"),
        expected_returncode=1,
        expected_stdout_fragments=(
            "Python checks",
            "fail_virtual_orders",
            "FAIL",
            "virtual orders failed",
        ),
        project_kind="virtual_failure",
        initialize_state=True,
    ),
    CheckCommandTestCase(
        description="run does not execute Python checks by default",
        command=("--no-color", "run"),
        expected_returncode=0,
        expected_stdout_fragments=("Execution  sqb run",),
        expected_absent_fragments=("Python checks", "check_orders_export"),
    ),
    CheckCommandTestCase(
        description="audit remains SQL audit only",
        command=("--no-color", "audit"),
        expected_returncode=0,
        expected_stdout_fragments=("Execution  sqb audit",),
        expected_absent_fragments=("Python checks", "check_orders_export"),
    ),
    CheckCommandTestCase(
        description="build no python suppresses read-side checks",
        command=("--no-color", "build", "--no-python"),
        expected_returncode=0,
        expected_stdout_fragments=("Completed successfully",),
        expected_absent_fragments=("Python checks", "check_orders_export"),
    ),
    CheckCommandTestCase(
        description="check command writes runtime target artifact",
        command=("--no-color", "check", "--select", "+tag:multi"),
        expected_returncode=0,
        expected_stdout_fragments=("check_order_customer_exports",),
        expected_file_fragments=(
            (
                "target/run/checks/python_checks.json",
                (
                    '"kind": "python_check"',
                    '"display_name": "check_order_customer_exports"',
                ),
            ),
        ),
    ),
)


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_python_checks_when_running_check_then_reports_expected_results(
    tmp_path: Path, test_case: CheckCommandTestCase
) -> None:
    project_dir: Path = prepare_check_project_by_kind(
        tmp_path=tmp_path,
        project_kind=test_case.project_kind,
    )
    initialize_state_when_requested(project_dir=project_dir, test_case=test_case)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=resolve_check_command(project_dir=project_dir, command=test_case.command),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode
    combined_output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in combined_output
    for fragment in test_case.expected_absent_fragments:
        assert fragment not in combined_output
    assert_expected_file_fragments(project_dir=project_dir, test_case=test_case)
