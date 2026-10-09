"""The fallback allow-list gate fails on sabotaged native stages and on stale entries."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential.main.differential import run_compiler_differential
from tests.e2e.scripts.compiler_differential._test_types import NativeFallbackGateTestCase
from tests.e2e.scripts.compiler_differential.helpers import (
    MODEL_ANALYSIS_SABOTAGE,
    REFERENCE_SCAN_SABOTAGE,
    harness_arguments,
    write_native_perturbation,
)

_VANISHED_ENTRY: str = (
    '\n[[entry]]\nengine = "native-preview"\nstage = "reference_extraction"\n'
    'site = "reference_extraction.scan"\nkind = "deferred"\ncounts = { project = 1 }\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeFallbackGateTestCase(
            description="recorded_list_passes",
            perturbation="",
            appended_entries="",
            expected_exit_code=0,
            expected_lines=("Compiler differential passed: 1 projects identical",),
        ),
        NativeFallbackGateTestCase(
            description="entry_that_no_longer_occurs_fails",
            perturbation="",
            appended_entries=_VANISHED_ENTRY,
            expected_exit_code=1,
            expected_lines=(
                "Native fallback allow-list: native-preview reference_extraction "
                "reference_extraction.scan deferred (project): listed but no longer occurs; "
                "remove it from the allow-list",
            ),
        ),
        NativeFallbackGateTestCase(
            description="shipped_reference_scan_sabotaged_to_python_fails",
            perturbation=REFERENCE_SCAN_SABOTAGE,
            appended_entries="",
            expected_exit_code=1,
            expected_lines=(
                "Native fallback allow-list: native-preview reference_extraction "
                "reference_extraction.scan deferred (project): ",
                "not on the allow-list; port it or list it with a reason",
            ),
        ),
        NativeFallbackGateTestCase(
            description="preview_model_analysis_sabotaged_to_python_fails",
            perturbation=MODEL_ANALYSIS_SABOTAGE,
            appended_entries="",
            expected_exit_code=1,
            expected_lines=(
                "Native fallback allow-list: native-preview model_analysis analysis_session "
                "session (project): ",
                "Compiler differential FAILED: 0 of 1 projects differ",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_allow_list_when_native_defers_more_or_less_then_the_gate_fails(
    test_case: NativeFallbackGateTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    allow_list: Path = tmp_path / "native_fallbacks.toml"
    recorded: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "record",
            extra=("--native-fallbacks", "update", "--native-fallback-list", str(allow_list)),
        )
    )
    _ = allow_list.write_text(
        allow_list.read_text(encoding="utf-8") + test_case.appended_entries, encoding="utf-8"
    )
    sabotage: Path = write_native_perturbation(tmp_path / "sabotage", source=test_case.perturbation)
    _ = capsys.readouterr()

    exit_code: int = run_compiler_differential(
        harness_arguments(
            work_dir=tmp_path / "check",
            extra=(
                "--native-fallbacks",
                "check",
                "--native-fallback-list",
                str(allow_list),
                "--engine-env",
                f"native-preview:PYTHONPATH={sabotage}",
            ),
        )
    )

    output: str = capsys.readouterr().out
    assert recorded == 0
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
