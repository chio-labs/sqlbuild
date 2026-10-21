"""Compile and plan read a native project's resources through their native views."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    CompiledViewFallbacksTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    compiled_view_fallbacks,
    copy_waffle_shop,
    write_orders_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CompiledViewFallbacksTestCase(
            description="compiling reads every model natively",
            write_project=write_orders_project,
            command=("compile", "--json", "--no-cache"),
            expected_exit_code=0,
            expected_fallbacks=0,
        ),
        CompiledViewFallbacksTestCase(
            description="planning reads every model natively",
            write_project=write_orders_project,
            command=("plan", "--json", "--no-cache"),
            expected_exit_code=0,
            expected_fallbacks=0,
        ),
        CompiledViewFallbacksTestCase(
            description="planning reads every source, seed, function and audit natively",
            write_project=copy_waffle_shop,
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
        project_dir=tmp_path / "project",
        write_project=test_case.write_project,
        command=test_case.command,
    )
    _ = capsys.readouterr()

    assert (exit_code, fallbacks) == (test_case.expected_exit_code, test_case.expected_fallbacks)
