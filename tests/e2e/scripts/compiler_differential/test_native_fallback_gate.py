"""The fallback allow-list gate fails on sabotaged native stages and on stale entries."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential.main.differential import run_compiler_differential
from tests.e2e.scripts.compiler_differential._test_types import NativeFallbackGateTestCase
from tests.e2e.scripts.compiler_differential.helpers import (
    MACRO_RESOLUTION_SABOTAGE,
    MODEL_ANALYSIS_SABOTAGE,
    RICH_LINEAGE_SABOTAGE,
    RICH_LINEAGE_SEED,
    harness_arguments,
    stage_disable_sabotage,
    write_native_perturbation,
)

_WAFFLE_SHOP_NATIVE_STAGES: tuple[str, ...] = (
    "attachments",
    "contracts",
    "lineage_facts",
    "macro_call_store",
    "macro_calls",
    "model_analysis",
    "semantic_checks",
)
_ANSWER_VANISHED: str = "native no longer answers here, so this work now runs in Python"
_FALLBACK_WITHOUT_ANSWERS: str = (
    "fallback disappeared but native answers did not appear; the stage may be switched off"
)
_VANISHED_ENTRY: str = (
    '\n[[entry]]\nengine = "native-preview"\nstage = "macro_calls"\n'
    'site = "macro_calls.resolution"\nkind = "deferred"\ncounts = { project = 1 }\n'
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
            description="entry_that_no_longer_occurs_without_new_native_answers_fails",
            perturbation="",
            appended_entries=_VANISHED_ENTRY,
            expected_exit_code=1,
            expected_lines=(
                "Native fallback allow-list: native-preview macro_calls "
                f"macro_calls.resolution deferred (project): {_FALLBACK_WITHOUT_ANSWERS}",
            ),
        ),
        NativeFallbackGateTestCase(
            description="shipped_macro_resolution_sabotaged_to_python_fails",
            perturbation=MACRO_RESOLUTION_SABOTAGE,
            appended_entries="",
            expected_exit_code=1,
            expected_lines=(
                "Native fallback allow-list: native-preview macro_calls "
                "macro_calls.resolution deferred (project): ",
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
        NativeFallbackGateTestCase(
            description="shipped_stages_switched_to_python_fail",
            perturbation=stage_disable_sabotage(("attachments", "macro_calls")),
            appended_entries="",
            expected_exit_code=1,
            expected_lines=(
                "Native fallback allow-list: native-preview attachments "
                f"attachments.native seed_pairs (project): {_ANSWER_VANISHED}",
                "Native fallback allow-list: native-preview macro_calls "
                f"macro_calls.native bridged_calls (project): {_ANSWER_VANISHED}",
                "Intended? Run `make compiler-baselines`",
            ),
        ),
        NativeFallbackGateTestCase(
            description="every_native_stage_switched_to_python_fails_by_name",
            perturbation=stage_disable_sabotage(_WAFFLE_SHOP_NATIVE_STAGES),
            appended_entries="",
            expected_exit_code=1,
            expected_lines=tuple(
                f"Native fallback allow-list: native-preview {stage} {stage}.native "
                for stage in _WAFFLE_SHOP_NATIVE_STAGES
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


@pytest.mark.parametrize(
    "test_case",
    [
        NativeFallbackGateTestCase(
            description="sql_test_glue_switched_off_is_not_a_finished_port",
            perturbation=stage_disable_sabotage(("sql_test_glue",)),
            appended_entries="",
            expected_exit_code=1,
            expected_lines=(
                "Native fallback allow-list: native-preview sql_test_glue sql_test_glue.native "
                f"sql_test_assemblies (fixture): {_ANSWER_VANISHED}",
                "Native fallback allow-list: native-preview sql_test_glue sql_test_glue.native "
                f"sql_test_plans (fixture): {_ANSWER_VANISHED}",
                "Native fallback allow-list: 2 problems",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_committed_allow_list_when_fallback_only_stage_is_switched_off_then_gate_refuses(
    test_case: NativeFallbackGateTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sabotage: Path = write_native_perturbation(tmp_path / "sabotage", source=test_case.perturbation)
    _ = capsys.readouterr()

    exit_code: int = run_compiler_differential(
        [
            "--corpus",
            "fixtures",
            "--jobs",
            "2",
            "--work-dir",
            str(tmp_path / "check"),
            "--native-fallbacks",
            "check",
            "--engine-env",
            f"native-preview:PYTHONPATH={sabotage}",
        ]
    )

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output


_RICH_SEED_ARGUMENTS: tuple[str, ...] = (
    "--corpus",
    "seeds",
    "--seed-start",
    str(RICH_LINEAGE_SEED),
    "--seeds",
    "1",
    "--jobs",
    "2",
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeFallbackGateTestCase(
            description="recorded_rich_lineage_passes",
            perturbation="",
            appended_entries="",
            expected_exit_code=0,
            expected_lines=("Compiler differential passed: 3 projects identical",),
        ),
        NativeFallbackGateTestCase(
            description="preview_rich_lineage_deferring_every_model_fails",
            perturbation=RICH_LINEAGE_SABOTAGE,
            appended_entries="",
            expected_exit_code=1,
            expected_lines=(
                "Native fallback allow-list: native-preview rich_lineage rich_lineage.native "
                f"rich_models (seed): {_ANSWER_VANISHED}",
                "Native fallback allow-list: native-preview rich_lineage rich_columns.py "
                "native_failure (seed): ",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_seed_with_rich_lineage_when_native_defers_every_model_then_the_gate_fails(
    test_case: NativeFallbackGateTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    allow_list: Path = tmp_path / "native_fallbacks.toml"
    recorded: int = run_compiler_differential(
        [
            *_RICH_SEED_ARGUMENTS,
            "--work-dir",
            str(tmp_path / "record"),
            "--native-fallbacks",
            "update",
            "--native-fallback-list",
            str(allow_list),
        ]
    )
    sabotage: Path = write_native_perturbation(tmp_path / "sabotage", source=test_case.perturbation)
    _ = capsys.readouterr()

    exit_code: int = run_compiler_differential(
        [
            *_RICH_SEED_ARGUMENTS,
            "--work-dir",
            str(tmp_path / "check"),
            "--native-fallbacks",
            "check",
            "--native-fallback-list",
            str(allow_list),
            "--engine-env",
            f"native-preview:PYTHONPATH={sabotage}",
        ]
    )

    output: str = capsys.readouterr().out
    assert recorded == 0
    assert exit_code == test_case.expected_exit_code, output
    assert all(line in output for line in test_case.expected_lines), output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
