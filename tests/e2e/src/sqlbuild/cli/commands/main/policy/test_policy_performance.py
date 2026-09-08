"""Opt-in performance guard for end-to-end policy evaluation."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    write_advanced_compile_project,
)
from tests.e2e.src.sqlbuild.cli.commands.main.policy._test_types import (
    PolicyPerformanceGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.policy.helpers import write_custom_policy_rules


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        PolicyPerformanceGuardTestCase(
            description="end-to-end policy checks 3000 advanced models within hard budget",
            model_count=3000,
            hard_ceiling_seconds=25,
            expected_max_elapsed_seconds=20.0,
            expected_returncode=1,
        ),
        PolicyPerformanceGuardTestCase(
            description="end-to-end policy checks 5000 advanced models within hard budget",
            model_count=5000,
            hard_ceiling_seconds=40,
            expected_max_elapsed_seconds=30.0,
            expected_returncode=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_advanced_project_and_disabled_cache_when_running_policy_then_finishes_within_budget(
    tmp_path: Path,
    test_case: PolicyPerformanceGuardTestCase,
) -> None:
    project_dir: Path = tmp_path / f"policy_advanced_{test_case.model_count}"
    write_advanced_compile_project(project_dir=project_dir, model_count=test_case.model_count)
    write_custom_policy_rules(project_dir=project_dir)
    config_path: Path = project_dir / "sqlbuild_project.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + (
            '\n[policy]\nselect = ["SQBP", "XSQBP"]\n'
            'rule_paths = ["policy/benchmark_rules.py"]\n\n'
            "[policy.cache]\nenabled = true\nrequire_cacheable = true\n"
        ),
        encoding="utf-8",
    )

    started_at: float = time.perf_counter()
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            "policy",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=test_case.hard_ceiling_seconds,
    )
    elapsed_seconds: float = time.perf_counter() - started_at

    assert result.returncode == test_case.expected_returncode
    assert '"fault_count"' in result.stdout
    assert elapsed_seconds <= test_case.expected_max_elapsed_seconds
