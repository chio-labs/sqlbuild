"""E2E coverage for per-target concurrency and its precedence."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    TargetConcurrencyE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    target_concurrency_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TargetConcurrencyE2ETestCase(
            description="the selected target's concurrency replaces the project setting",
            target_concurrency="concurrency = 3\n",
            local_settings="",
            command=("--no-color", "build", "--verbose", "--target", "ci"),
            expected_fragment="3 configured limit (targets.ci.concurrency)",
        ),
        TargetConcurrencyE2ETestCase(
            description="--concurrency overrides the target",
            target_concurrency="concurrency = 3\n",
            local_settings="",
            command=("--no-color", "build", "--verbose", "--target", "ci", "--concurrency", "1"),
            expected_fragment="1 configured limit (--concurrency)",
        ),
        TargetConcurrencyE2ETestCase(
            description="the target overrides a local settings override",
            target_concurrency="concurrency = 3\n",
            local_settings="[settings]\nconcurrency = 5\n",
            command=("--no-color", "build", "--verbose", "--target", "ci"),
            expected_fragment="3 configured limit (targets.ci.concurrency)",
        ),
        TargetConcurrencyE2ETestCase(
            description="a target without concurrency keeps the local settings override",
            target_concurrency="",
            local_settings="[settings]\nconcurrency = 5\n",
            command=("--no-color", "build", "--verbose", "--target", "ci"),
            expected_fragment="5 configured limit (sqlbuild_local.toml settings.concurrency)",
        ),
        TargetConcurrencyE2ETestCase(
            description="a local target concurrency overrides the project target",
            target_concurrency="concurrency = 3\n",
            local_settings="[targets.ci]\nconcurrency = 4\n",
            command=("--no-color", "build", "--verbose", "--target", "ci"),
            expected_fragment="4 configured limit (targets.ci.concurrency)",
        ),
        TargetConcurrencyE2ETestCase(
            description="other targets keep the project setting",
            target_concurrency="concurrency = 3\n",
            local_settings="",
            command=("--no-color", "build", "--verbose"),
            expected_fragment="2 configured limit (settings.concurrency)",
        ),
        TargetConcurrencyE2ETestCase(
            description="seed uses the target's concurrency",
            target_concurrency="concurrency = 3\n",
            local_settings="",
            command=("--no-color", "seed", "--target", "ci"),
            expected_fragment="concurrency: 3",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_concurrency_when_running_then_documented_precedence_applies(
    tmp_path: Path,
    test_case: TargetConcurrencyE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="target_concurrency",
        repo_files=target_concurrency_project_files(
            target_concurrency=test_case.target_concurrency,
            local_settings=test_case.local_settings,
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command, project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert test_case.expected_fragment in result.stdout + result.stderr
    assert table_exists(db_path=project_dir / "warehouse.duckdb", table_name="products")


@pytest.mark.parametrize(
    "test_case",
    [
        TargetConcurrencyE2ETestCase(
            description="zero is rejected with a coded configuration error",
            target_concurrency="concurrency = 0\n",
            local_settings="",
            command=("--no-color", "build", "--target", "ci"),
            expected_fragment="targets.ci.concurrency must be an integer >= 1",
        ),
        TargetConcurrencyE2ETestCase(
            description="a non-integer is rejected with a coded configuration error",
            target_concurrency='concurrency = "8"\n',
            local_settings="",
            command=("--no-color", "build", "--target", "ci"),
            expected_fragment="targets.ci.concurrency must be an integer >= 1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_target_concurrency_when_running_then_config_error_is_coded(
    tmp_path: Path,
    test_case: TargetConcurrencyE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="target_concurrency",
        repo_files=target_concurrency_project_files(
            target_concurrency=test_case.target_concurrency,
            local_settings=test_case.local_settings,
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command, project_dir=project_dir
    )
    output: str = result.stdout + result.stderr

    assert result.returncode != 0
    assert "D001" in output
    assert test_case.expected_fragment in output
    assert not (project_dir / "warehouse.duckdb").exists()
