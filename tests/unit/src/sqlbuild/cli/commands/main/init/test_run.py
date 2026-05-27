from __future__ import annotations

from pathlib import Path

import pytest

import sqlbuild.cli.commands.main.init as init_module
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
                "sources",
                "seeds",
                "loaders",
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
                "sources/.gitkeep",
                "seeds/.gitkeep",
                "loaders/.gitkeep",
                "tests/unit/.gitkeep",
                "tests/scenarios/.gitkeep",
                "functions/sql/.gitkeep",
                "functions/python/.gitkeep",
                "macros/.gitkeep",
                "audits/.gitkeep",
            ),
            expected_config_fragment='name = "demo_project"',
        )
    ],
    ids=["creates blank project directories for all resource types"],
)
def test_given_empty_directory_when_running_init_then_scaffolds_project_directories(
    test_case: InitScaffoldTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / test_case.project_dir_name
    project_dir.mkdir()
    monkeypatch.setattr(init_module, "update_sqlbuild_skills", lambda *, project_dir: None)

    result: int = init_module.run_init(project_dir)

    assert result == 0
    assert test_case.expected_config_fragment in (project_dir / "sqlbuild_project.toml").read_text(
        encoding="utf-8"
    )
    assert (
        tuple(
            directory
            for directory in test_case.expected_directories
            if (project_dir / directory).is_dir()
        )
        == test_case.expected_directories
    )
    assert (
        tuple(
            gitkeep
            for gitkeep in test_case.expected_gitkeep_files
            if (project_dir / gitkeep).is_file()
        )
        == test_case.expected_gitkeep_files
    )
