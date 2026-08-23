from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

import sqlbuild.cli.commands.main.workspace._init as init_module
from tests.unit.src.sqlbuild.cli.commands.main.init._test_types import InitScaffoldTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        InitScaffoldTestCase(
            description="creates blank project directories for all resource types",
            project_dir_name="demo-project",
            expected_directories=(
                "models/staging",
                "models/marts",
                "schemas",
                "sources",
                "seeds",
                "loaders",
                "tasks",
                "assets",
                "checks",
                "hooks",
                "tests/unit",
                "tests/scenarios",
                "functions/sql",
                "functions/python",
                "macros",
                "audits",
            ),
            expected_gitkeep_files=(
                "models/staging/.gitkeep",
                "models/marts/.gitkeep",
                "schemas/.gitkeep",
                "sources/.gitkeep",
                "seeds/.gitkeep",
                "loaders/.gitkeep",
                "tasks/.gitkeep",
                "assets/.gitkeep",
                "checks/.gitkeep",
                "hooks/.gitkeep",
                "tests/unit/.gitkeep",
                "tests/scenarios/.gitkeep",
                "functions/sql/.gitkeep",
                "functions/python/.gitkeep",
                "macros/.gitkeep",
                "audits/.gitkeep",
            ),
            expected_config_fragment='name = "demo_project"',
            expected_stdout_fragments=(
                "SQLBuild project created",
                "Project: demo_project",
                "Config:  sqlbuild_project.toml",
                "Next steps:",
                "1. Add sources to sources/",
                "2. Add seeds to seeds/ or loaders to loaders/",
                "3. Add tasks to tasks/, assets to assets/, or checks to checks/",
                "4. Add hooks to hooks/, functions to functions/, or macros to macros/",
                "7. sqb compile",
                "8. sqb build",
            ),
            expected_color_fragments=(
                "\033[34m\033[1mSQLBuild project created\033[0m",
                "  \033[34mProject\033[0m: demo_project",
                "\033[1mNext steps\033[0m:",
                "  7. \033[2msqb compile\033[0m",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_directory_when_running_init_then_scaffolds_project_directories(
    test_case: InitScaffoldTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / test_case.project_dir_name
    project_dir.mkdir()
    monkeypatch.setattr(init_module, "update_sqlbuild_skills", lambda *, project_dir: None)
    monkeypatch.setattr(init_module, "supports_color", lambda: False)

    result: int = init_module.run_init(project_dir)

    captured: CaptureResult[str] = capsys.readouterr()
    assert result == 0
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in captured.out
    assert test_case.expected_config_fragment in (project_dir / "sqlbuild_project.toml").read_text(
        encoding="utf-8"
    )
    assert all((project_dir / directory).is_dir() for directory in test_case.expected_directories)
    assert all((project_dir / gitkeep).is_file() for gitkeep in test_case.expected_gitkeep_files)


@pytest.mark.parametrize(
    "test_case",
    [
        InitScaffoldTestCase(
            description="styles init heading",
            project_dir_name="color-project",
            expected_directories=(),
            expected_gitkeep_files=(),
            expected_config_fragment='name = "color_project"',
            expected_color_fragments=(
                "\033[34m\033[1mSQLBuild project created\033[0m",
                "  \033[34mProject\033[0m: color_project",
                "\033[1mNext steps\033[0m:",
                "  7. \033[2msqb compile\033[0m",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_color_terminal_when_running_init_then_it_styles_heading(
    test_case: InitScaffoldTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / test_case.project_dir_name
    project_dir.mkdir()
    monkeypatch.setattr(init_module, "update_sqlbuild_skills", lambda *, project_dir: None)
    monkeypatch.setattr(init_module, "supports_color", lambda: True)

    result: int = init_module.run_init(project_dir)

    captured: CaptureResult[str] = capsys.readouterr()
    assert result == 0
    expected_color_fragment: str
    for expected_color_fragment in test_case.expected_color_fragments:
        assert expected_color_fragment in captured.out
