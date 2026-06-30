"""E2E tests for sqb audit command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.audit._test_types import AuditE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    assert_fragments_in_order,
    prepare_waffle_shop,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AuditE2ETestCase(
            description="audit runs all audits against built relations and all pass",
            expected_exit_code=0,
            expected_stdout_fragment="PASS=28",
            expected_stdout_fragments=(
                "Execution  sqb audit  (concurrency: 1)",
                "Connecting to duckdb...",
                "Connected to duckdb.",
            ),
            expected_ordered_stdout_fragments=(
                "Execution  sqb audit  (concurrency: 1)",
                "Connecting to duckdb...",
                "Connected to duckdb. (<time>)",
                "Inspecting warehouse state...",
                "Generated plan. (<time>)",
                "Audit (28 selected, 12 models)",
                "Connecting to duckdb...",
                "Connected to duckdb. (<time>)",
                "customer_status_snapshot",
                "PASS=<n>  WARN=<n>  FAIL=<n>  TOTAL=<n>",
            ),
        ),
    ],
    ids=["audit runs all audits against built relations and all pass"],
)
def test_given_waffle_shop_project_when_running_audit_then_all_audits_pass(
    test_case: AuditE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)

    run_sqb(command=("--no-color", "build"), project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "audit"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    assert_fragments_in_order(result.stdout, test_case.expected_ordered_stdout_fragments)
