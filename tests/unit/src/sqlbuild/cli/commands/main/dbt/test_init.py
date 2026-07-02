from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

import sqlbuild.cli.commands.main.commands.dbt_init as dbt_init_module
from sqlbuild.cli.commands.helpers.dbt_init.prompt import resolve_production_git_ref
from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.models import DbtInitRequest, DbtInitResult
from tests.unit.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtInitOutputTestCase,
    DbtInitProjectDirDefaultTestCase,
    DbtInitPromptTestCase,
    DbtInitValidationOrderTestCase,
)

DBT_INIT_PROMPT_TEST_CASES: list[DbtInitPromptTestCase] = [
    DbtInitPromptTestCase(
        description="uses explicit production git ref without prompting",
        explicit_git_ref="release/prod",
        input_text="ignored\n",
        input_is_tty=True,
        expected_git_ref="release/prod",
    ),
    DbtInitPromptTestCase(
        description="defaults to main in non interactive runs",
        explicit_git_ref=None,
        input_text="prod\n",
        input_is_tty=False,
        expected_git_ref="main",
    ),
    DbtInitPromptTestCase(
        description="reads production git ref from interactive input",
        explicit_git_ref=None,
        input_text="prod\n",
        input_is_tty=True,
        expected_git_ref="prod",
        expected_output_fragments=(
            "dbt production reuse setup",
            "Production git ref [main]:",
        ),
    ),
    DbtInitPromptTestCase(
        description="uses main when interactive input is blank",
        explicit_git_ref=None,
        input_text="\n",
        input_is_tty=True,
        expected_git_ref="main",
        expected_output_fragments=("Production git ref [main]:",),
    ),
    DbtInitPromptTestCase(
        description="uses main when interactive input is whitespace",
        explicit_git_ref=None,
        input_text="   \t  \n",
        input_is_tty=True,
        expected_git_ref="main",
        expected_output_fragments=("Production git ref [main]:",),
    ),
    DbtInitPromptTestCase(
        description="uses main when interactive input reaches eof",
        explicit_git_ref=None,
        input_text="",
        input_is_tty=True,
        expected_git_ref="main",
        expected_output_fragments=("Production git ref [main]:",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DBT_INIT_PROMPT_TEST_CASES,
    ids=[case.description for case in DBT_INIT_PROMPT_TEST_CASES],
)
def test_given_dbt_init_prompt_inputs_when_resolving_prod_ref_then_returns_expected_ref(
    test_case: DbtInitPromptTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_stream: StringIO = StringIO(test_case.input_text)
    output_stream: StringIO = StringIO()
    monkeypatch.setattr(input_stream, "isatty", lambda: test_case.input_is_tty)

    result: str = resolve_production_git_ref(
        explicit_git_ref=test_case.explicit_git_ref,
        input_stream=input_stream,
        output_stream=output_stream,
        use_color=False,
    )

    assert result == test_case.expected_git_ref
    output_text: str = output_stream.getvalue()
    expected_fragment: str
    for expected_fragment in test_case.expected_output_fragments:
        assert expected_fragment in output_text


@pytest.mark.parametrize(
    "test_case",
    [
        DbtInitOutputTestCase(
            description="init outputs progress and dbt-first next steps",
            dry_run=False,
            expected_fragments=(
                "Inspecting dbt project and profile...",
                "Inspected dbt project and profile.",
                "SQLBuild project created",
                "Setup summary:",
                "Config file",
                "/workspace/sqlbuild_project/sqlbuild_project.toml",
                "Production git ref",
                "main",
                "Production schema macro",
                "/workspace/sqlbuild_project/dbt/macros/generate_schema_name.sql",
                "What SQLBuild created:",
                "SQLBuild twin config",
                "Production schema macro",
                "This file lives in the SQLBuild project, not your dbt project.",
                "It must make dbt resolve models to production schemas",
                "sqb dbt debug",
                "sqb dbt build",
            ),
            unexpected_fragments=("Add SQLBuild models",),
        )
    ],
    ids=["init outputs progress and dbt-first next steps"],
)
def test_given_dbt_init_when_running_then_outputs_progress_and_dbt_first_next_steps(
    test_case: DbtInitOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
        assert request.progress_callbacks.start is not None
        assert request.progress_callbacks.complete is not None
        request.progress_callbacks.start("Inspecting dbt project and profile...")
        request.progress_callbacks.complete("Inspected dbt project and profile.")
        return DbtInitResult(
            output_dir=Path("/workspace/sqlbuild_project"),
            project_file=Path("/workspace/sqlbuild_project/sqlbuild_project.toml"),
            project_name="analytics",
            macro_file=Path("/workspace/sqlbuild_project/dbt/macros/generate_schema_name.sql"),
            production_git_ref="main",
            adapter="duckdb",
            target_name="dev",
            profile_name="analytics_profile",
            toml='name = "analytics"\n',
        )

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt_init.run_dbt_profile_init",
        run_dbt_profile_init,
    )
    monkeypatch.setattr(
        dbt_init_module,
        "_validate_dbt_profile_init_request",
        lambda *, request: None,
    )

    exit_code: int = dbt_init_module.run_dbt_init_command(
        cwd=Path("/workspace"),
        dbt_project_dir="dbt_project",
        profiles_dir="profiles",
        profile_name=None,
        target_name=None,
        sqb_output_dir="sqlbuild_project",
        dry_run=test_case.dry_run,
        overwrite=False,
        skip_dbt_debug=True,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    for fragment in test_case.expected_fragments:
        assert fragment in captured.out
    for fragment in test_case.unexpected_fragments:
        assert fragment not in captured.out


@pytest.mark.parametrize(
    "test_case",
    [
        DbtInitOutputTestCase(
            description="dry-run outputs progress and preview document",
            dry_run=True,
            expected_fragments=(
                "Rendering dbt profile connection...",
                "Rendered dbt profile connection.",
                "SQLBuild project preview",
                "Production git ref: release/prod",
                "Production schema macro: "
                "/workspace/sqlbuild_project/dbt/macros/generate_schema_name.sql",
                "Generated config:",
                'source = "dbt_profile"',
            ),
        )
    ],
    ids=["dry-run outputs progress and preview document"],
)
def test_given_dbt_init_dry_run_when_running_then_outputs_preview_document(
    test_case: DbtInitOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
        assert request.progress_callbacks.start is not None
        assert request.progress_callbacks.complete is not None
        request.progress_callbacks.start("Rendering dbt profile connection...")
        request.progress_callbacks.complete("Rendered dbt profile connection.")
        return DbtInitResult(
            output_dir=Path("/workspace/sqlbuild_project"),
            project_file=Path("/workspace/sqlbuild_project/sqlbuild_project.toml"),
            project_name="analytics",
            macro_file=Path("/workspace/sqlbuild_project/dbt/macros/generate_schema_name.sql"),
            production_git_ref="release/prod",
            adapter="duckdb",
            target_name="dev",
            profile_name="analytics_profile",
            toml=(
                'name = "analytics"\n'
                'adapter = "duckdb"\n'
                "\n"
                "[targets.dev.connection]\n"
                'source = "dbt_profile"\n'
            ),
            dry_run=True,
        )

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt_init.run_dbt_profile_init",
        run_dbt_profile_init,
    )
    monkeypatch.setattr(
        dbt_init_module,
        "_validate_dbt_profile_init_request",
        lambda *, request: None,
    )

    exit_code: int = dbt_init_module.run_dbt_init_command(
        cwd=Path("/workspace"),
        dbt_project_dir="dbt_project",
        profiles_dir="profiles",
        profile_name=None,
        target_name=None,
        sqb_output_dir="sqlbuild_project",
        dry_run=test_case.dry_run,
        overwrite=False,
        skip_dbt_debug=True,
        production_git_ref="release/prod",
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    for fragment in test_case.expected_fragments:
        assert fragment in captured.out
    for fragment in test_case.unexpected_fragments:
        assert fragment not in captured.out


@pytest.mark.parametrize(
    "test_case",
    [
        DbtInitOutputTestCase(
            description="init output uses SQLBuild colors when terminal supports color",
            dry_run=False,
            expected_fragments=(),
            expected_color_fragments=(
                "\033[2mInspecting dbt project and profile...\033[0m",
                "\033[32m\033[1mSQLBuild project created\033[0m",
                "\033[1mSetup summary\033[0m:",
                "\033[34m\033[1mProject",
                "analytics",
                "\033[1mWhat SQLBuild created\033[0m:",
                "\033[34m\033[1mSQLBuild twin config\033[0m",
                "\033[1mNext steps\033[0m:",
                "\033[33mReview the config file and production schema macro above.\033[0m",
                "  3. \033[2msqb dbt debug\033[0m",
                "  4. \033[2msqb dbt build\033[0m",
            ),
        )
    ],
    ids=["init output uses SQLBuild colors when terminal supports color"],
)
def test_given_color_terminal_when_running_dbt_init_then_it_styles_output(
    test_case: DbtInitOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
        assert request.progress_callbacks.start is not None
        assert request.progress_callbacks.complete is not None
        request.progress_callbacks.start("Inspecting dbt project and profile...")
        request.progress_callbacks.complete("Inspected dbt project and profile.")
        return DbtInitResult(
            output_dir=Path("/workspace/sqlbuild_project"),
            project_file=Path("/workspace/sqlbuild_project/sqlbuild_project.toml"),
            project_name="analytics",
            macro_file=Path("/workspace/sqlbuild_project/dbt/macros/generate_schema_name.sql"),
            production_git_ref="main",
            adapter="duckdb",
            target_name="dev",
            profile_name="analytics_profile",
            toml='name = "analytics"\n',
        )

    monkeypatch.setattr(dbt_init_module, "supports_color", lambda: True)
    monkeypatch.setattr(
        dbt_init_module,
        "run_dbt_profile_init",
        run_dbt_profile_init,
    )
    monkeypatch.setattr(
        dbt_init_module,
        "_validate_dbt_profile_init_request",
        lambda *, request: None,
    )

    exit_code: int = dbt_init_module.run_dbt_init_command(
        cwd=Path("/workspace"),
        dbt_project_dir="dbt_project",
        profiles_dir="profiles",
        profile_name=None,
        target_name=None,
        sqb_output_dir="sqlbuild_project",
        dry_run=test_case.dry_run,
        overwrite=False,
        skip_dbt_debug=True,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    for fragment in test_case.expected_color_fragments:
        assert fragment in captured.out


@pytest.mark.parametrize(
    "test_case",
    [
        DbtInitProjectDirDefaultTestCase(
            description="defaults project dir to cwd when dbt project file exists",
            dbt_project_text="name: analytics\nprofile: analytics\n",
            expected_dbt_project_dir=".",
        )
    ],
    ids=["defaults project dir to cwd when dbt project file exists"],
)
def test_given_dbt_project_in_cwd_when_running_dbt_init_then_project_dir_defaults_to_cwd(
    test_case: DbtInitProjectDirDefaultTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "dbt_project.yml").write_text(test_case.dbt_project_text, encoding="utf-8")
    captured_request: dict[str, DbtInitRequest] = {}

    def validate_dbt_profile_init_request(*, request: DbtInitRequest) -> None:
        assert request.dbt_project_dir == Path(test_case.expected_dbt_project_dir)

    def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
        captured_request["request"] = request
        return DbtInitResult(
            output_dir=tmp_path / "sqlbuild_project",
            project_file=tmp_path / "sqlbuild_project" / "sqlbuild_project.toml",
            project_name="analytics",
            macro_file=tmp_path / "sqlbuild_project" / "dbt/macros/generate_schema_name.sql",
            production_git_ref="main",
            adapter="duckdb",
            target_name="dev",
            profile_name="analytics",
            toml='name = "analytics"\n',
        )

    monkeypatch.setattr(
        dbt_init_module, "_validate_dbt_profile_init_request", validate_dbt_profile_init_request
    )
    monkeypatch.setattr(dbt_init_module, "run_dbt_profile_init", run_dbt_profile_init)

    exit_code: int = dbt_init_module.run_dbt_init_command(
        cwd=tmp_path,
        dbt_project_dir=None,
        profiles_dir=None,
        profile_name=None,
        target_name=None,
        sqb_output_dir=None,
        dry_run=True,
        overwrite=False,
        skip_dbt_debug=True,
        production_git_ref="main",
    )

    assert exit_code == 0
    assert captured_request["request"].dbt_project_dir == Path(test_case.expected_dbt_project_dir)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtInitValidationOrderTestCase(
            description="validates init inputs before prompting for production ref",
            input_text="prod\n",
            expected_error_fragment="profiles.yml",
            unexpected_output_fragments=("Production git ref",),
        )
    ],
    ids=["validates init inputs before prompting for production ref"],
)
def test_given_invalid_dbt_init_inputs_when_running_then_validation_happens_before_prompt(
    test_case: DbtInitValidationOrderTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_stream: StringIO = StringIO(test_case.input_text)
    monkeypatch.setattr(input_stream, "isatty", lambda: True)
    monkeypatch.setattr(dbt_init_module.sys, "stdin", input_stream)

    def validate_dbt_profile_init_request(*, request: DbtInitRequest) -> None:
        raise DbtProfileError(f"dbt config file not found: {test_case.expected_error_fragment}")

    def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
        raise AssertionError("init should not run after validation failure")

    monkeypatch.setattr(
        dbt_init_module, "_validate_dbt_profile_init_request", validate_dbt_profile_init_request
    )
    monkeypatch.setattr(dbt_init_module, "run_dbt_profile_init", run_dbt_profile_init)

    with pytest.raises(DbtProfileError, match=test_case.expected_error_fragment):
        dbt_init_module.run_dbt_init_command(
            cwd=tmp_path,
            dbt_project_dir=".",
            profiles_dir=None,
            profile_name=None,
            target_name=None,
            sqb_output_dir=None,
            dry_run=True,
            overwrite=False,
            skip_dbt_debug=True,
            production_git_ref=None,
        )

    captured: CaptureResult[str] = capsys.readouterr()
    for fragment in test_case.unexpected_output_fragments:
        assert fragment not in captured.out
