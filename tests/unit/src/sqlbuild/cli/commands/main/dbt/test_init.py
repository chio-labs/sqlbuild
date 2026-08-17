from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

import sqlbuild.cli.commands._helpers.dbt_init.execution as dbt_init_execution
import sqlbuild.cli.commands._helpers.dbt_init.invocation as dbt_init_invocation
import sqlbuild.cli.commands.main.dbt._dbt_init as dbt_init_module
from sqlbuild.cli.commands.models import DbtInitCommandRequest
from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.models import DbtInitRequest, DbtInitResult
from tests.unit.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtInitOutputTestCase,
    DbtInitProjectDirDefaultTestCase,
    DbtInitValidationOrderTestCase,
)


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
                "What SQLBuild created:",
                "SQLBuild twin config",
                "This points SQLBuild at your dbt project and profile.",
                "sqb dbt debug",
                "sqb dbt build",
            ),
            unexpected_fragments=("Add SQLBuild models", "Production git ref"),
        )
    ],
    ids=lambda case: case.description,
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
            adapter="duckdb",
            target_name="dev",
            profile_name="analytics_profile",
            toml='name = "analytics"\n',
        )

    monkeypatch.setattr(dbt_init_execution, "run_dbt_profile_init", run_dbt_profile_init)
    monkeypatch.setattr(
        dbt_init_invocation,
        "_validate_dbt_profile_init_request",
        lambda *, request: None,
    )

    exit_code: int = dbt_init_module.run_dbt_init_command(
        DbtInitCommandRequest(
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
                "Generated config:",
                'source = "dbt_profile"',
            ),
            unexpected_fragments=("Production git ref", "Production schema macro"),
        )
    ],
    ids=lambda case: case.description,
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

    monkeypatch.setattr(dbt_init_execution, "run_dbt_profile_init", run_dbt_profile_init)
    monkeypatch.setattr(
        dbt_init_invocation,
        "_validate_dbt_profile_init_request",
        lambda *, request: None,
    )

    exit_code: int = dbt_init_module.run_dbt_init_command(
        DbtInitCommandRequest(
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
                "\033[33mReview the config file above.\033[0m",
                "  3. \033[2msqb dbt debug\033[0m",
                "  4. \033[2msqb dbt build\033[0m",
            ),
        )
    ],
    ids=lambda case: case.description,
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
            adapter="duckdb",
            target_name="dev",
            profile_name="analytics_profile",
            toml='name = "analytics"\n',
        )

    monkeypatch.setattr(dbt_init_invocation, "supports_color", lambda: True)
    monkeypatch.setattr(dbt_init_execution, "run_dbt_profile_init", run_dbt_profile_init)
    monkeypatch.setattr(
        dbt_init_invocation,
        "_validate_dbt_profile_init_request",
        lambda *, request: None,
    )

    exit_code: int = dbt_init_module.run_dbt_init_command(
        DbtInitCommandRequest(
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
    ids=lambda case: case.description,
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
            adapter="duckdb",
            target_name="dev",
            profile_name="analytics",
            toml='name = "analytics"\n',
        )

    monkeypatch.setattr(
        dbt_init_invocation,
        "_validate_dbt_profile_init_request",
        validate_dbt_profile_init_request,
    )
    monkeypatch.setattr(dbt_init_execution, "run_dbt_profile_init", run_dbt_profile_init)

    exit_code: int = dbt_init_module.run_dbt_init_command(
        DbtInitCommandRequest(
            cwd=tmp_path,
            dbt_project_dir=None,
            profiles_dir=None,
            profile_name=None,
            target_name=None,
            sqb_output_dir=None,
            dry_run=True,
            overwrite=False,
            skip_dbt_debug=True,
        )
    )

    assert exit_code == 0
    assert captured_request["request"].dbt_project_dir == Path(test_case.expected_dbt_project_dir)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtInitValidationOrderTestCase(
            description="validates init inputs before running init",
            expected_error_fragment="profiles.yml",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_dbt_init_inputs_when_running_then_validation_happens_before_init(
    test_case: DbtInitValidationOrderTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def validate_dbt_profile_init_request(*, request: DbtInitRequest) -> None:
        raise DbtProfileError(f"dbt config file not found: {test_case.expected_error_fragment}")

    def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
        raise AssertionError("init should not run after validation failure")

    monkeypatch.setattr(
        dbt_init_invocation,
        "_validate_dbt_profile_init_request",
        validate_dbt_profile_init_request,
    )
    monkeypatch.setattr(dbt_init_execution, "run_dbt_profile_init", run_dbt_profile_init)

    with pytest.raises(DbtProfileError, match=test_case.expected_error_fragment):
        dbt_init_module.run_dbt_init_command(
            DbtInitCommandRequest(
                cwd=tmp_path,
                dbt_project_dir=".",
                profiles_dir=None,
                profile_name=None,
                target_name=None,
                sqb_output_dir=None,
                dry_run=True,
                overwrite=False,
                skip_dbt_debug=True,
            )
        )
