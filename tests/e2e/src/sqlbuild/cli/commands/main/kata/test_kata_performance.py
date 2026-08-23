"""Opt-in performance guard for end-to-end kata evaluation."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    write_advanced_compile_project,
)
from tests.e2e.src.sqlbuild.cli.commands.main.kata._test_types import (
    KataPerformanceGuardTestCase,
)


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        KataPerformanceGuardTestCase(
            description="end-to-end kata checks 3000 advanced models within hard budget",
            model_count=3000,
            expected_max_seconds=5.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_advanced_project_and_disabled_cache_when_running_kata_then_finishes_within_budget(
    tmp_path: Path,
    test_case: KataPerformanceGuardTestCase,
) -> None:
    project_dir: Path = tmp_path / f"kata_advanced_{test_case.model_count}"
    write_advanced_compile_project(project_dir=project_dir, model_count=test_case.model_count)
    config_path: Path = project_dir / "sqlbuild_project.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + '\n[kata]\nselect = ["SQBK"]\n\n[kata.cache]\nenabled = false\n',
        encoding="utf-8",
    )

    start: float = time.perf_counter()
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            "kata",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    elapsed_seconds: float = time.perf_counter() - start

    assert result.returncode == 1
    assert '"fault_count"' in result.stdout
    assert elapsed_seconds < test_case.expected_max_seconds
