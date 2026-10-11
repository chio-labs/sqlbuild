"""Goldens recorded from the oracle pass an unchanged check and pinpoint any edited output."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential.main.differential import run_compiler_differential
from tests.e2e.scripts.compiler_differential._test_types import GoldenOutputTestCase
from tests.e2e.scripts.compiler_differential.helpers import (
    harness_arguments,
    write_failure_case_project,
)

_CASE: str = "engine-error-week-date-cursor-start"
_PROJECT: str = "orders"
_ENGINE_ARGUMENTS: tuple[str, ...] = (
    "--engines",
    "native",
    "native-preview",
    "--expect",
    "failure:P001",
)


@pytest.mark.parametrize(
    "test_case",
    [
        GoldenOutputTestCase(
            description="unchanged_goldens_pass_for_both_engines",
            golden_edit=("", ""),
            expected_exit_code=0,
            expected_lines=("Compiler differential passed: 1 projects identical",),
        ),
        GoldenOutputTestCase(
            description="edited_error_text_fails_for_both_engines",
            golden_edit=("hour must be in 0..23", "hour must be in 1..24"),
            expected_exit_code=1,
            expected_lines=(
                "  - golden (native) at /commands/0/diagnostics/0/message",
                "  - golden (native-preview) at /commands/0/diagnostics/0/message",
                "Compiler differential FAILED: 1 of 1 projects differ",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_goldens_when_checking_then_only_edited_outputs_differ(
    test_case: GoldenOutputTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project: Path = write_failure_case_project(tmp_path / _PROJECT, name=_CASE)
    golden_dir: Path = tmp_path / "goldens"
    recorded: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "record",
            project=project,
            extra=(*_ENGINE_ARGUMENTS, "--goldens", "update", "--golden-dir", str(golden_dir)),
        )
    )
    golden: Path = golden_dir / "project" / f"{_PROJECT}.json"
    _ = golden.write_text(
        golden.read_text(encoding="utf-8").replace(*test_case.golden_edit), encoding="utf-8"
    )
    _ = capsys.readouterr()

    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "check",
            project=project,
            extra=(*_ENGINE_ARGUMENTS, "--goldens", "check", "--golden-dir", str(golden_dir)),
        )
    )

    output: str = capsys.readouterr().out
    assert recorded == 0
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
