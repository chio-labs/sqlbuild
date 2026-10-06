"""E2E tests for default TO targets, the guarded default full diff and multi-value flags."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.diff._test_types import (
    DefaultFullDiffE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.diff.helpers import (
    build_both_environments,
    prepare_diff_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

_SMALL_DEV_LIMIT: str = "\n[targets.dev.diff]\nmax_full_rows = 1\n"
_UNLIMITED: str = (
    '\n[targets.prod.diff]\nmax_full_rows = "unlimited"\n'
    '\n[targets.dev.diff]\nmax_full_rows = "unlimited"\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        DefaultFullDiffE2ETestCase(
            description="bare FROM compares with the active target and runs a full diff",
            command=(
                "--no-color",
                "diff",
                "prod",
                "--select",
                "orders_snapshot",
                "customer_totals",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "prod vs dev",
                "orders_snapshot",
                "customer_totals",
                "No changed columns.",
            ),
        ),
        DefaultFullDiffE2ETestCase(
            description="table over the TO limit stops before reading data",
            command=(
                "--no-color",
                "diff",
                "prod",
                "--select",
                "orders_snapshot",
                "customer_totals",
            ),
            local_config_suffix=_SMALL_DEV_LIMIT,
            expected_exit_code=2,
            expected_stderr_fragments=(
                "error[C270]: full diff stopped before reading data: 2 of 2 selected models",
                "orders_snapshot: prod 3 rows, limit 10,000,000; dev 3 rows, limit 1",
                "customer_totals: prod 2 rows, limit 10,000,000; dev 2 rows, limit 1; no cursor",
                "Run one of these instead:",
                "sqb --project-dir {project_dir} diff prod:dev --full "
                "--select orders_snapshot customer_totals",
                "sqb --project-dir {project_dir} diff prod:dev --schema-only "
                "--select orders_snapshot customer_totals",
            ),
            unexpected_stdout_fragments=("No changed columns.",),
        ),
        DefaultFullDiffE2ETestCase(
            description="model with a cursor offers a bounded command",
            command=("--no-color", "diff", "prod", "--select", "orders_snapshot"),
            local_config_suffix=_SMALL_DEV_LIMIT,
            expected_exit_code=2,
            expected_stderr_fragments=(
                "sqb --project-dir {project_dir} diff prod:dev --bounded <window> "
                "--select orders_snapshot",
            ),
        ),
        DefaultFullDiffE2ETestCase(
            description="view with unknown size is blocked at the default limit",
            command=("--no-color", "diff", "prod", "--select", "stg_orders"),
            expected_exit_code=2,
            expected_stderr_fragments=(
                "stg_orders: prod size unknown: no table size metadata (view or missing table), "
                "limit 10,000,000",
            ),
        ),
        DefaultFullDiffE2ETestCase(
            description="unlimited targets skip the guard",
            command=("--no-color", "diff", "prod", "--select", "stg_orders", "--key", "order_id"),
            local_config_suffix=_UNLIMITED,
            expected_exit_code=0,
            expected_stdout_fragments=("stg_orders", "No changed columns."),
        ),
        DefaultFullDiffE2ETestCase(
            description="explicit full bypasses the guard",
            command=("--no-color", "diff", "prod", "--full", "--select", "orders_snapshot"),
            local_config_suffix=_SMALL_DEV_LIMIT,
            expected_exit_code=0,
            expected_stdout_fragments=("No changed columns.",),
        ),
        DefaultFullDiffE2ETestCase(
            description="explicit schema only bypasses the guard",
            command=("--no-color", "diff", "prod", "--schema-only", "--select", "stg_orders"),
            expected_exit_code=0,
            expected_stdout_fragments=("No schema differences.",),
        ),
        DefaultFullDiffE2ETestCase(
            description="two mode flags are rejected",
            command=(
                "--no-color",
                "diff",
                "prod",
                "--full",
                "--schema-only",
                "--select",
                "orders_snapshot",
            ),
            expected_exit_code=1,
            expected_stderr_fragments=("diff accepts at most one of --full, --schema-only",),
        ),
        DefaultFullDiffE2ETestCase(
            description="bare FROM equal to the active target is rejected",
            command=("--no-color", "diff", "dev", "--select", "orders_snapshot"),
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[C272]: diff FROM 'dev' is the active target",
                "pass both targets as FROM:TO",
            ),
        ),
        DefaultFullDiffE2ETestCase(
            description="key and exclude column take several values",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders_snapshot",
                "--key",
                "order_id",
                "customer_id",
                "--exclude-column",
                "status",
                "amount_cents",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=("order_id, customer_id", "No changed columns."),
        ),
        DefaultFullDiffE2ETestCase(
            description="query mode key takes several values",
            command=(
                "--no-color",
                "diff",
                "--left-query",
                "SELECT 1 AS order_id, 1 AS line_number, 5 AS amount UNION ALL SELECT 1, 2, 7",
                "--right-query",
                "SELECT 1 AS order_id, 1 AS line_number, 5 AS amount UNION ALL SELECT 1, 2, 7",
                "--key",
                "order_id",
                "line_number",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=("order_id, line_number",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_diff_without_mode_when_running_then_size_guard_and_defaults_apply(
    test_case: DefaultFullDiffE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    local_config_path: Path = project_dir / "sqlbuild_local.toml"
    local_config_path.write_text(
        local_config_path.read_text(encoding="utf-8") + test_case.local_config_suffix,
        encoding="utf-8",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_exit_code, output
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, output
    for fragment in test_case.expected_stderr_fragments:
        assert fragment.format(project_dir=project_dir) in result.stderr, output
    for fragment in test_case.unexpected_stdout_fragments:
        assert fragment not in result.stdout, output


@pytest.mark.parametrize(
    "test_case",
    [
        DefaultFullDiffE2ETestCase(
            description="json output carries the blocked sizes and commands",
            command=("--no-color", "diff", "prod:dev", "--select", "orders_snapshot", "--json"),
            local_config_suffix=_SMALL_DEV_LIMIT,
            expected_exit_code=2,
            expected_json_status="incomplete",
            expected_json_blocked_models=("orders_snapshot",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_blocked_default_full_diff_when_writing_json_then_document_carries_guard_details(
    test_case: DefaultFullDiffE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    local_config_path: Path = project_dir / "sqlbuild_local.toml"
    local_config_path.write_text(
        local_config_path.read_text(encoding="utf-8") + test_case.local_config_suffix,
        encoding="utf-8",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["status"] == test_case.expected_json_status
    size_guard: dict[str, Any] = payload["size_guard"]
    assert [model["name"] for model in size_guard["models"]] == list(
        test_case.expected_json_blocked_models
    )
    assert size_guard["models"][0]["to"] == {
        "detail": None,
        "exceeds_limit": True,
        "max_full_rows": 1,
        "relation": size_guard["models"][0]["to"]["relation"],
        "row_count": 3,
        "target": "dev",
    }
    assert size_guard["commands"]["full"] == (
        f"sqb --project-dir {project_dir} diff prod:dev --full --select orders_snapshot"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
