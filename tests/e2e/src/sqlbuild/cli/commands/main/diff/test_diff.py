"""E2E tests for sqb diff command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.diff._test_types import (
    DiffCommandE2ETestCase,
    DiffKeyFailureE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.diff.helpers import (
    build_both_environments,
    execute_duckdb,
    prepare_diff_project,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

DIFF_COMMAND_E2E_TEST_CASES: list[DiffCommandE2ETestCase] = [
    DiffCommandE2ETestCase(
        description="identical full diff returns zero",
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=0,
        expected_stdout_fragments=(
            "orders_snapshot",
            "No schema differences.",
            "No changed columns.",
        ),
    ),
    DiffCommandE2ETestCase(
        description="row mismatch returns nonzero and reports column mismatch",
        mutation_sql=(
            "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 5 WHERE order_id = 1",
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=1,
        expected_stdout_fragments=(
            "joined: 3",
            "unequal",
            "amount_cents",
            "mismatches=1",
            "order_id=1 | 100 -> 105",
        ),
    ),
    DiffCommandE2ETestCase(
        description="concise side only samples are shown by default",
        mutation_sql=(
            "DELETE FROM dev.orders_sparse WHERE order_id = 1",
            "INSERT INTO dev.orders_sparse (order_id, customer_id) VALUES (99, 9)",
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_sparse",
        ),
        expected_exit_code=1,
        expected_stdout_fragments=(
            "prod only",
            "order_id=1",
            "dev only",
            "order_id=99",
        ),
    ),
    DiffCommandE2ETestCase(
        description="concise multi column examples show multiple changed columns",
        mutation_sql=(
            (
                "UPDATE dev.orders_snapshot SET customer_id = 99, "
                "amount_cents = amount_cents + 5 WHERE order_id = 1"
            ),
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=1,
        expected_stdout_fragments=(
            "customer_id",
            "amount_cents",
            "order_id=1 | 1 -> 99",
            "order_id=1 | 100 -> 105",
        ),
    ),
    DiffCommandE2ETestCase(
        description="verbose diff shows example row changes",
        mutation_sql=(
            "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 5 WHERE order_id = 1",
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--verbose",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=1,
        expected_stdout_fragments=(
            "Examples",
            "order_id=1 | 100 -> 105",
        ),
    ),
    DiffCommandE2ETestCase(
        description="verbose diff shows side only key samples",
        mutation_sql=(
            "DELETE FROM dev.orders_sparse WHERE order_id = 1",
            "INSERT INTO dev.orders_sparse (order_id, customer_id) VALUES (99, 9)",
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--verbose",
            "--select",
            "orders_sparse",
        ),
        expected_exit_code=1,
        expected_stdout_fragments=(
            "prod only",
            "order_id=1",
            "dev only",
            "order_id=99",
        ),
    ),
    DiffCommandE2ETestCase(
        description="excluded column changes are ignored",
        mutation_sql=("UPDATE dev.orders_snapshot SET status = 'surprising' WHERE order_id = 1",),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=0,
        expected_stdout_fragments=("No changed columns.",),
    ),
    DiffCommandE2ETestCase(
        description="tolerance pass stays clean",
        mutation_sql=(
            "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 1 WHERE order_id = 1",
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=0,
        expected_stdout_fragments=("No changed columns.",),
    ),
    DiffCommandE2ETestCase(
        description="tolerance fail reports mismatch",
        mutation_sql=(
            "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 2 WHERE order_id = 1",
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=1,
        expected_stdout_fragments=(
            "amount_cents",
            "mismatches=1",
            "order_id=1 | 100 -> 102",
        ),
    ),
    DiffCommandE2ETestCase(
        description="multi model output uses global header and divider",
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_snapshot",
            "customer_totals",
        ),
        expected_exit_code=0,
        expected_stdout_fragments=(
            "selected models: 2",
            "orders_snapshot",
            "customer_totals",
            "────────────────",
        ),
    ),
    DiffCommandE2ETestCase(
        description="example caps can be overridden",
        mutation_sql=(
            "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 5 WHERE order_id = 1",
            "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 7 WHERE order_id = 2",
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--max-column-examples",
            "2",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=1,
        expected_stdout_fragments=(
            "order_id=1 | 100 -> 105",
            "order_id=2 | 200 -> 207",
        ),
    ),
    DiffCommandE2ETestCase(
        description="schema only ignores row drift",
        mutation_sql=(
            "UPDATE dev.orders_snapshot SET amount_cents = amount_cents + 5 WHERE order_id = 1",
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--schema-only",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=0,
        expected_stdout_fragments=("No schema differences.", "order_id"),
    ),
    DiffCommandE2ETestCase(
        description="bounded fallback on cursorless model succeeds",
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--bounded",
            "30d",
            "--select",
            "customer_totals",
        ),
        expected_exit_code=0,
        expected_stdout_fragments=(
            "Fallback",
            "no cursor configured; used full row diff",
            "No changed columns.",
        ),
    ),
    DiffCommandE2ETestCase(
        description="missing unique key fails clearly",
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "daily_revenue",
        ),
        expected_exit_code=1,
        expected_stderr_fragments=("model 'daily_revenue' requires unique_key for row diff",),
    ),
    DiffCommandE2ETestCase(
        description="environment schemas auto-create through real cli build flow",
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_snapshot",
        ),
        expected_exit_code=0,
        expected_stdout_fragments=("orders_snapshot",),
    ),
]

DIFF_KEY_FAILURE_E2E_TEST_CASES: list[DiffKeyFailureE2ETestCase] = [
    DiffKeyFailureE2ETestCase(
        description="null unique key fails clearly",
        mutation_sql=("UPDATE dev.orders_snapshot SET order_id = NULL WHERE order_id = 3",),
        expected_stderr_fragment="row diff right relation contains null unique_key values",
    ),
    DiffKeyFailureE2ETestCase(
        description="duplicate unique key fails clearly",
        mutation_sql=("UPDATE dev.orders_snapshot SET order_id = 2 WHERE order_id = 3",),
        expected_stderr_fragment="row diff right relation contains duplicate unique_key values",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DIFF_COMMAND_E2E_TEST_CASES,
    ids=[case.description for case in DIFF_COMMAND_E2E_TEST_CASES],
)
def test_given_diff_project_when_running_diff_then_behavior_matches_expected(
    test_case: DiffCommandE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    db_path: Path = project_dir / "diff.duckdb"

    mutation_sql: str
    for mutation_sql in test_case.mutation_sql:
        execute_duckdb(db_path=db_path, sql=mutation_sql)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr, result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    DIFF_KEY_FAILURE_E2E_TEST_CASES,
    ids=[case.description for case in DIFF_KEY_FAILURE_E2E_TEST_CASES],
)
def test_given_invalid_dev_keys_when_running_diff_then_it_fails_clearly(
    test_case: DiffKeyFailureE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    db_path: Path = project_dir / "diff.duckdb"

    mutation_sql: str
    for mutation_sql in test_case.mutation_sql:
        execute_duckdb(db_path=db_path, sql=mutation_sql)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "orders_snapshot",
        ),
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert test_case.expected_stderr_fragment in result.stderr, result.stdout + result.stderr
