"""A machine-output document printed by one in-process command never hides the next one's error."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sqlbuild._native import run_cli
from tests.integration.src.sqlbuild.cli.entry._test_types import MachineOutputResetTestCase
from tests.integration.src.sqlbuild.cli.entry.helpers import write_janitor_project


@pytest.mark.parametrize(
    "test_case",
    [
        MachineOutputResetTestCase(
            description="a recall settings error after a janitor json run prints its document",
            first_args=("janitor", "--json"),
            failing_args=("janitor", "--json"),
            failing_extra_toml=(
                '\n[connections.history]\nadapter = "sqlite"\npath = "history.sqlite3"\n\n'
                '[recall]\nwrite_connection = "history"\n'
            ),
            expected_error_code="C975",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_janitor_json_success_when_next_command_fails_early_then_error_document_prints(
    test_case: MachineOutputResetTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    succeeding: Path = write_janitor_project(tmp_path / "succeeding", extra_toml="")
    failing: Path = write_janitor_project(
        tmp_path / "failing", extra_toml=test_case.failing_extra_toml
    )

    _ = run_cli(["--project-dir", str(succeeding), *test_case.first_args])
    first: dict[str, Any] = json.loads(capsys.readouterr().out)
    _ = run_cli(["--project-dir", str(failing), *test_case.failing_args])
    second: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert first["status"] == "disabled"
    assert second["error"]["code"] == test_case.expected_error_code
