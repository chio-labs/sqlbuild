from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.workspace._playground import run_playground
from sqlbuild.cli.commands.models import PlaygroundCommandRequest
from tests.e2e.src.sqlbuild.cli.commands.main.playground._test_types import (
    LegacyCodePageOutputTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        LegacyCodePageOutputTestCase(
            description="cp1252 streams still get the UTF-8 summary and valid JSON",
            code_page="cp1252",
            expected_summary="\u2713 Project compiled",
            expected_json_command="compile",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_legacy_code_page_streams_when_compiling_then_output_is_utf8(
    test_case: LegacyCodePageOutputTestCase, tmp_path: Path
) -> None:
    assert run_playground(PlaygroundCommandRequest(project_dir=tmp_path, target_path="shop")) == 0
    environment: dict[str, str] = {"PYTHONIOENCODING": test_case.code_page}

    summary: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=tmp_path / "shop", env=environment
    )
    machine: subprocess.CompletedProcess[str] = run_sqb(
        command=("compile", "--json"), project_dir=tmp_path / "shop", env=environment
    )

    assert (
        summary.returncode,
        test_case.expected_summary in summary.stdout,
        machine.returncode,
        json.loads(machine.stdout).get("command"),
    ) == (0, True, 0, test_case.expected_json_command), summary.stderr + machine.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
