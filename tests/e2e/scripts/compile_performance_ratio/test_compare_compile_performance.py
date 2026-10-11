"""End-to-end tests for the same-runner compile performance ratio guard."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.scripts.compile_performance_ratio._test_types import (
    CompilePerformanceRatioTestCase,
    EnginePhaseRatioTestCase,
    PerSideCompilePerformanceRatioTestCase,
)
from tests.e2e.scripts.compile_performance_ratio.helpers import (
    FAILING_GENERATOR,
    MARKER_GENERATOR,
    logged_projects,
    write_fake_base_root,
    write_logging_python,
)

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    "test_case",
    (
        CompilePerformanceRatioTestCase(
            description="identical builds pass a generous limit",
            kind="dense",
            models=20,
            max_ratio="3.0",
            expected_return_code=0,
            expected_fragments=(
                "dense 20 models, cold compile without cache: head vs base",
                "dense 20 models, unchanged warm compile: head vs base",
                "dense 20 models, one-model edit on a warm cache: head vs base",
                "| Wall (s) |",
                "| CPU (s) |",
                "| analysis_native_ms |",
                "**Result: passed.**",
            ),
        ),
        CompilePerformanceRatioTestCase(
            description="an unattainable limit fails with the exceeded ratios",
            kind="dense",
            models=20,
            max_ratio="0.01",
            expected_return_code=1,
            expected_fragments=(
                "Compile performance regression: dense 20 cold: wall ratio",
                "dense 20 warm: CPU ratio",
                "dense 20 edit: wall ratio",
                "**Result: failed.**",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_two_builds_when_comparing_compile_performance_then_enforces_ratio_limit(
    test_case: CompilePerformanceRatioTestCase,
) -> None:
    environment: dict[str, str] = dict(os.environ)
    _ = environment.pop("GITHUB_STEP_SUMMARY", None)
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.compare_compile_performance",
            "--kind",
            test_case.kind,
            "--models",
            str(test_case.models),
            "--runs",
            "1",
            "--base-python",
            sys.executable,
            "--head-python",
            sys.executable,
            "--max-ratio",
            test_case.max_ratio,
            "--noise-floor-seconds",
            "0",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_return_code, output
    for fragment in test_case.expected_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    (
        PerSideCompilePerformanceRatioTestCase(
            description="each build compiles the project its own generator wrote",
            base_generator=MARKER_GENERATOR,
            expected_return_code=0,
            expected_fragments=("Projects generated per side",),
            # Cold warm-up and run, then cache priming and a run for warm and for edit per
            # side; head also compiles uncached after warm and edit to check equality.
            expected_base_projects=("base",) * 6,
            expected_head_projects=("head",) * 8,
        ),
        PerSideCompilePerformanceRatioTestCase(
            description="a failing base generator stops before any compile",
            base_generator=FAILING_GENERATOR,
            expected_return_code=1,
            expected_fragments=("base project generation in", "base generator exploded"),
            expected_base_projects=(),
            expected_head_projects=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_base_root_when_comparing_compile_performance_then_each_side_uses_its_project(
    test_case: PerSideCompilePerformanceRatioTestCase, tmp_path: Path
) -> None:
    base_root: Path = write_fake_base_root(
        root=tmp_path / "base", generator=test_case.base_generator
    )
    base_log: Path = tmp_path / "base.log"
    head_log: Path = tmp_path / "head.log"
    base_python: Path = write_logging_python(path=tmp_path / "base-python", log=base_log)
    head_python: Path = write_logging_python(path=tmp_path / "head-python", log=head_log)
    environment: dict[str, str] = dict(os.environ)
    _ = environment.pop("GITHUB_STEP_SUMMARY", None)

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.compare_compile_performance",
            "--kind",
            "dense",
            "--models",
            "20",
            "--runs",
            "1",
            "--base-root",
            str(base_root),
            "--base-python",
            str(base_python),
            "--head-python",
            str(head_python),
            "--max-ratio",
            "1000",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_return_code, output
    assert all(fragment in output for fragment in test_case.expected_fragments), output
    assert logged_projects(base_log) == test_case.expected_base_projects
    assert logged_projects(head_log) == test_case.expected_head_projects


@pytest.mark.parametrize(
    "test_case",
    (
        EnginePhaseRatioTestCase(
            description="native-preview contracts within a generous limit of native's",
            max_ratio="1000",
            phase_noise_floor_ms="1000",
            expected_return_code=0,
            expected_fragments=(
                "Engines: base `native`, head `native-preview`.",
                "Gated phases: contracts_cpu_ms.",
                "| contracts_cpu_ms |",
                "**Result: passed.**",
            ),
        ),
        EnginePhaseRatioTestCase(
            description="a gated phase over its allowance fails on that phase alone",
            max_ratio="0",
            phase_noise_floor_ms="-1",
            expected_return_code=1,
            expected_fragments=(
                "Compile performance regression: dense 20 cold contracts_cpu_ms:",
                "**Result: failed.**",
            ),
        ),
        EnginePhaseRatioTestCase(
            description="model analysis CPU over its allowance with rules off fails on it alone",
            max_ratio="0",
            phase_noise_floor_ms="-1",
            expected_return_code=1,
            expected_fragments=(
                "Compile arguments: `--select=*`.",
                "| model_analysis_cpu_ms |",
                "Compile performance regression: dense 20 cold model_analysis_cpu_ms:",
            ),
            gate_phase="model_analysis_cpu_ms",
            compile_args=("--compile-arg=--select=*",),
        ),
        EnginePhaseRatioTestCase(
            description="custom rule CPU over its allowance fails on it alone",
            max_ratio="0",
            phase_noise_floor_ms="-1",
            expected_return_code=1,
            expected_fragments=(
                "Gated phases: custom_rules_cpu_ms.",
                "| custom_rules_cpu_ms |",
                "Compile performance regression: dense 20 cold custom_rules_cpu_ms:",
            ),
            gate_phase="custom_rules_cpu_ms",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_two_engines_when_gating_a_phase_then_enforces_only_that_phase(
    test_case: EnginePhaseRatioTestCase,
) -> None:
    environment: dict[str, str] = dict(os.environ)
    _ = environment.pop("GITHUB_STEP_SUMMARY", None)
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.compare_compile_performance",
            "--kind",
            "dense",
            "--models",
            "20",
            "--modes",
            "cold",
            "--runs",
            "1",
            "--base-python",
            sys.executable,
            "--head-python",
            sys.executable,
            "--base-engine",
            "native",
            "--head-engine",
            "native-preview",
            "--gate-phase",
            test_case.gate_phase,
            "--max-ratio",
            test_case.max_ratio,
            "--phase-noise-floor-ms",
            test_case.phase_noise_floor_ms,
            *test_case.compile_args,
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_return_code, output
    assert all(fragment in output for fragment in test_case.expected_fragments), output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
