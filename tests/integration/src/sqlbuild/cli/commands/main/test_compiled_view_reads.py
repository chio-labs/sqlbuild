"""Compile and plan read a native project's models through its native views."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    CompiledViewFallbacksTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import compiled_view_fallbacks


@pytest.mark.parametrize(
    "test_case",
    [
        CompiledViewFallbacksTestCase(
            description="compiling reads every model natively",
            command=("compile", "--json", "--no-cache"),
            expected_exit_code=0,
            expected_fallbacks=0,
        ),
        CompiledViewFallbacksTestCase(
            description="planning reads every model natively",
            command=("plan", "--json", "--no-cache"),
            expected_exit_code=0,
            expected_fallbacks=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_project_when_running_then_no_model_read_falls_back_to_python(
    test_case: CompiledViewFallbacksTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, fallbacks = compiled_view_fallbacks(
        project_dir=tmp_path / "project", command=test_case.command
    )
    _ = capsys.readouterr()

    assert (exit_code, fallbacks) == (test_case.expected_exit_code, test_case.expected_fallbacks)
