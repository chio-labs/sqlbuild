from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

import sqlbuild.cli.commands.main.dbt_init as dbt_init_module
from sqlbuild.integrations.dbt.models import DbtInitRequest, DbtInitResult
from tests.unit.src.sqlbuild.cli.commands.main.dbt._test_types import DbtInitOutputTestCase


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
            adapter="duckdb",
            target_name="dev",
            profile_name="analytics_profile",
            toml='name = "analytics"\n',
        )

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.dbt_init.run_dbt_profile_init",
        run_dbt_profile_init,
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
        "sqlbuild.cli.commands.main.dbt_init.run_dbt_profile_init",
        run_dbt_profile_init,
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
            description="init output uses SQLBuild colors when terminal supports color",
            dry_run=False,
            expected_fragments=(),
            expected_color_fragments=(
                "\033[2mInspecting dbt project and profile...\033[0m",
                "\033[32m\033[1mSQLBuild project created\033[0m",
                "  \033[34m\033[1mProject\033[0m: analytics",
                "\033[1mNext steps\033[0m:",
                "  2. \033[2msqb dbt debug\033[0m",
                "  3. \033[2msqb dbt build\033[0m",
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
