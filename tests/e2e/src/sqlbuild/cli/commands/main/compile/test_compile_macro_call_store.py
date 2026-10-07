"""Compiles that reuse stored macro call results must match an uncached compile after every edit."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    BrokenMacroCallStoreKeyTestCase,
    MacroCallStoreEditSequenceTestCase,
    MacroCallStoreEditStep,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    MACRO_CALL_STORE_ENGINE,
    STORE_ENVIRONMENT_REGION_VAR,
    CompileReuseRun,
    MacroCallStoreRun,
    edit_label_helper,
    edit_south_model,
    freeze_macro_call_store_environment,
    in_process_reuse_run,
    macro_call_store_compile,
    prepare_macro_call_store_project,
    replace_project_text,
    run_reuse_compile,
    write_project_file,
    write_store_flavor,
)
from tests.integration.src.sqlbuild.compiler.compile.helpers import MACRO_CALL_LOG_ENV_VAR

_EDIT_STEPS: tuple[MacroCallStoreEditStep, ...] = (
    MacroCallStoreEditStep(
        description="no_change",
        edit=lambda _root: None,
        expected_logged_calls=0,
    ),
    MacroCallStoreEditStep(
        description="model_comment",
        edit=lambda root: edit_south_model(root, "FROM (", "-- reviewed\nFROM ("),
        expected_logged_calls=0,
    ),
    MacroCallStoreEditStep(
        description="model_adds_a_call",
        edit=lambda root: edit_south_model(
            root, "  @target_label()", '  @logged("tax") AS logged_tax,\n  @target_label()'
        ),
        expected_logged_calls=1,
    ),
    MacroCallStoreEditStep(
        description="model_private_constant_read_by_context_macro",
        edit=lambda root: edit_south_model(root, "_south_bonus 3", "_south_bonus 4"),
        expected_logged_calls=0,
    ),
    MacroCallStoreEditStep(
        description="cli_vars_read_by_context_macro",
        edit=lambda _root: None,
        expected_logged_calls=0,
        args=("--vars", '{"region": "south"}'),
    ),
    MacroCallStoreEditStep(
        description="target_read_by_context_macro",
        edit=lambda _root: None,
        expected_logged_calls=0,
        args=("--target", "prod"),
    ),
    MacroCallStoreEditStep(
        description="environment_variable_read_by_macro",
        edit=lambda _root: None,
        expected_logged_calls=2,
        env=((STORE_ENVIRONMENT_REGION_VAR, "south"),),
    ),
    MacroCallStoreEditStep(
        description="project_var_edit",
        edit=lambda root: replace_project_text(
            root, "sqlbuild_project.toml", 'region = "north"', 'region = "east"'
        ),
        expected_logged_calls=2,
    ),
    MacroCallStoreEditStep(
        description="constant_file_edit",
        edit=lambda root: replace_project_text(
            root, "constants/base_rate.sql", "value 1)", "value 5)"
        ),
        expected_logged_calls=2,
    ),
    MacroCallStoreEditStep(
        description="enum_edit",
        edit=lambda root: replace_project_text(
            root, "enums/order_status.sql", 'PLACED "placed"', 'PLACED "open"'
        ),
        expected_logged_calls=2,
    ),
    MacroCallStoreEditStep(
        description="macro_body_edit",
        edit=lambda root: replace_project_text(
            root, "macros/common.py", 'return f"{column} * 100"', 'return f"{column} * 1000"'
        ),
        expected_logged_calls=2,
    ),
    MacroCallStoreEditStep(
        description="helper_module_edit",
        edit=lambda root: edit_label_helper(root, "other"),
        expected_logged_calls=2,
    ),
    MacroCallStoreEditStep(
        description="macro_file_added",
        edit=lambda root: (
            write_project_file(
                root,
                "macros/badges.py",
                'def badge() -> str:\n    """Return a badge literal."""\n    return "\'gold\'"\n',
            ),
            edit_south_model(root, "  @label() AS label,\n", "  @badge() AS badge,\n"),
        ),
        expected_logged_calls=2,
    ),
    MacroCallStoreEditStep(
        description="macro_file_removed",
        edit=lambda root: (
            edit_south_model(root, "  @badge() AS badge,\n", ""),
            (root / "macros/badges.py").unlink(),
        ),
        expected_logged_calls=2,
    ),
    MacroCallStoreEditStep(
        description="outside_module_rewritten_in_place",
        edit=lambda root: write_store_flavor(extlib=root.parent / "extlib", value="salty"),
        expected_logged_calls=2,
    ),
    MacroCallStoreEditStep(
        description="model_comment_after_every_edit",
        edit=lambda root: edit_south_model(root, "-- reviewed\n", "-- reviewed twice\n"),
        expected_logged_calls=0,
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        MacroCallStoreEditSequenceTestCase(
            description="full_render_each_step", project_reuse=False, steps=_EDIT_STEPS
        ),
        MacroCallStoreEditSequenceTestCase(
            description="with_project_and_render_reuse", project_reuse=True, steps=_EDIT_STEPS
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edit_sequence_when_compiling_with_macro_call_store_then_each_step_matches_uncached(
    tmp_path: Path, test_case: MacroCallStoreEditSequenceTestCase
) -> None:
    project_dir: Path = tmp_path / "project"
    extlib: Path = tmp_path / "extlib"
    log_path: Path = tmp_path / "macro-calls.log"
    prepare_macro_call_store_project(project_dir=project_dir, extlib=extlib)
    cold: MacroCallStoreRun = macro_call_store_compile(
        project_dir=project_dir,
        extlib=extlib,
        log_path=log_path,
        project_reuse=test_case.project_reuse,
    )
    assert (cold.incremental.returncode, cold.matches) == (0, True), cold.incremental.stderr

    for step in test_case.steps:
        _ = step.edit(project_dir)
        run: MacroCallStoreRun = macro_call_store_compile(
            project_dir=project_dir,
            extlib=extlib,
            log_path=log_path,
            project_reuse=test_case.project_reuse,
            args=step.args,
            extra_env=step.env,
        )

        assert run.incremental.returncode == 0, (step.description, run.incremental.stderr)
        assert run.matches is test_case.expected_matches_uncached, step.description
        assert run.logged_calls == step.expected_logged_calls, step.description


@pytest.mark.parametrize(
    "test_case",
    [
        BrokenMacroCallStoreKeyTestCase(
            description="helper_module_edit",
            edit=lambda root: edit_label_helper(root, "other"),
            expected_matches_uncached=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_broken_store_key_when_compiling_an_edit_then_the_oracle_reports_a_mismatch(
    tmp_path: Path,
    test_case: BrokenMacroCallStoreKeyTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / "project"
    extlib: Path = tmp_path / "extlib"
    prepare_macro_call_store_project(project_dir=project_dir, extlib=extlib)
    monkeypatch.syspath_prepend(str(extlib))
    monkeypatch.setenv("SQLBUILD_COMPILER_ENGINE", MACRO_CALL_STORE_ENGINE)
    monkeypatch.setenv("SQLBUILD_DISABLE_COMPILE_REUSE", "1")
    monkeypatch.setenv(MACRO_CALL_LOG_ENV_VAR, str(tmp_path / "macro-calls.log"))
    freeze_macro_call_store_environment(monkeypatch)
    cold: CompileReuseRun = in_process_reuse_run(project_dir=project_dir, capsys=capsys)
    assert cold.returncode == 0, cold.stderr
    test_case.edit(project_dir)

    broken: CompileReuseRun = in_process_reuse_run(project_dir=project_dir, capsys=capsys)
    reference: CompileReuseRun = run_reuse_compile(
        project_dir=project_dir,
        env={"PYTHONPATH": str(extlib), "SQLBUILD_COMPILER_ENGINE": MACRO_CALL_STORE_ENGINE},
        args=("--no-cache",),
    )

    assert (broken.returncode, reference.returncode) == (0, 0)
    assert (broken.compiled == reference.compiled) is test_case.expected_matches_uncached
