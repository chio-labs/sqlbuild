"""E2E coverage of local scenario replay over VARIANT fixtures, which need current DuckDB storage."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scenario._test_types import (
    LocalVariantScenarioTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    build_local_variant_scenario_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        LocalVariantScenarioTestCase(
            description="a captured VARIANT fixture replays locally in strict mode",
            repo_files=build_local_variant_scenario_project_files(),
            scenario_name="orders__keep_payload",
            expected_stdout_fragment="PASS=1  FAIL=0  ERROR=0  SKIP=0  TOTAL=1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_captured_variant_fixture_when_replaying_locally_then_the_scenario_passes(
    test_case: LocalVariantScenarioTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="local_variant", repo_files=test_case.repo_files
    )
    captured: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "scenario", "capture", test_case.scenario_name),
        project_dir=project_dir,
    )
    assert captured.returncode == 0, captured.stdout + captured.stderr

    replayed: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "scenario",
            "test",
            "--local",
            "--strict",
            test_case.scenario_name,
        ),
        project_dir=project_dir,
    )

    assert replayed.returncode == 0, replayed.stdout + replayed.stderr
    assert "X699" not in replayed.stdout
    assert test_case.expected_stdout_fragment in replayed.stdout
