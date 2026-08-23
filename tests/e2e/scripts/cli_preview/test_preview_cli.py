"""End-to-end tests for the real CLI preview runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.scripts.cli_preview._test_types import PreviewCliTestCase

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    "test_case",
    (
        PreviewCliTestCase(
            description="compile scene renders production compile output",
            scene="compile",
            arguments=("--no-color",),
            expected_return_code=0,
            expected_fragments=("compile: compile summary", "Compile ready", "stg_orders"),
            unexpected_fragments=("\033[",),
        ),
        PreviewCliTestCase(
            description="expected failure scene normalizes its exit code",
            scene="test-error",
            arguments=(),
            expected_return_code=0,
            expected_fragments=("ERROR", "Failures:", "[T002]"),
            unexpected_fragments=("\033[", "0 mismatched", "error[T002]"),
        ),
        PreviewCliTestCase(
            description="virtual promotion scene runs a real branch lifecycle",
            scene="virtual-promote",
            arguments=("--no-color",),
            expected_return_code=0,
            expected_fragments=(
                "virtual-promote: promote a branch virtual environment into dev",
                "Virtual promotion complete",
                "promoted models",
            ),
            unexpected_fragments=("\033[",),
        ),
        PreviewCliTestCase(
            description="virtual reconcile scene reports healthy persisted state",
            scene="virtual-reconcile",
            arguments=("--no-color",),
            expected_return_code=0,
            expected_fragments=("Virtual reconcile", "Reconcile report for dev: no issues."),
            unexpected_fragments=("\033[",),
        ),
        PreviewCliTestCase(
            description="virtual janitor scene renders cleanup decisions",
            scene="virtual-janitor",
            arguments=("--no-color",),
            expected_return_code=0,
            expected_fragments=("Janitor preview", "Skipped objects", "virtual state pruned"),
            unexpected_fragments=("\033[",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_preview_scene_when_running_cli_then_renders_real_command_output(
    test_case: PreviewCliTestCase,
) -> None:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        args=(
            sys.executable,
            "-m",
            "scripts.preview_cli",
            test_case.scene,
            *test_case.arguments,
        ),
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == test_case.expected_return_code
    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in result.stdout
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in result.stdout
