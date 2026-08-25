from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    DirectModeVirtualFlagGuardE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectModeVirtualFlagGuardE2ETestCase(
            description="plan rejects --virtual-env on a direct-mode project",
            command=("--no-color", "plan", "--virtual-env", "pr_123"),
            expected_error_fragment=(
                "plan does not support --virtual-env unless virtual_environments = true"
            ),
        ),
        DirectModeVirtualFlagGuardE2ETestCase(
            description="plan rejects --include-stale-upstreams on a direct-mode project",
            command=("--no-color", "plan", "--include-stale-upstreams"),
            expected_error_fragment=(
                "plan does not support --include-stale-upstreams unless virtual_environments = true"
            ),
        ),
        DirectModeVirtualFlagGuardE2ETestCase(
            description="build rejects --virtual-env on a direct-mode project",
            command=("--no-color", "build", "--virtual-env", "pr_123"),
            expected_error_fragment=(
                "build does not support --virtual-env unless virtual_environments = true"
            ),
        ),
        DirectModeVirtualFlagGuardE2ETestCase(
            description="build rejects --include-stale-upstreams on a direct-mode project",
            command=("--no-color", "build", "--include-stale-upstreams"),
            expected_error_fragment=(
                "build does not support --include-stale-upstreams unless "
                "virtual_environments = true"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_direct_mode_project_when_passing_virtual_only_flags_then_command_fails(
    test_case: DirectModeVirtualFlagGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_mode_flag_guard",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_mode_flag_guard"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS order_id\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    combined_output: str = result.stdout + result.stderr
    assert test_case.expected_error_fragment in combined_output
