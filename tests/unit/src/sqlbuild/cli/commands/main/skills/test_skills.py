from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.skills.models import SkillUpdateResult
from sqlbuild.cli.commands._helpers.skills.update import (
    ensure_generated_marker,
    generated_marker,
    update_sqlbuild_skills,
)
from sqlbuild.cli.exceptions import CliUserError
from tests.unit.src.sqlbuild.cli.commands.main.skills._test_types import (
    SkillUpdateErrorTestCase,
    SkillUpdateTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.skills.helpers import (
    prepare_skill_update_project,
    read_relative_file,
    write_project_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SkillUpdateTestCase(
            description="writes all local skill targets by default",
            expected_written_paths=(
                Path(".opencode/skills/sqlbuild/SKILL.md"),
                Path(".claude/skills/sqlbuild/SKILL.md"),
                Path(".agents/skills/sqlbuild/SKILL.md"),
            ),
        ),
        SkillUpdateTestCase(
            description="uses project configured skill targets",
            project_config='name = "demo"\nadapter = "duckdb"\n\n[skills]\ntargets = ["opencode"]\n',
            expected_written_paths=(Path(".opencode/skills/sqlbuild/SKILL.md"),),
        ),
        SkillUpdateTestCase(
            description="requested targets override project configured targets",
            project_config='name = "demo"\nadapter = "duckdb"\n\n[skills]\ntargets = ["claude"]\n',
            requested_targets=("agents",),
            expected_written_paths=(Path(".agents/skills/sqlbuild/SKILL.md"),),
        ),
        SkillUpdateTestCase(
            description="force overwrites non generated skill file",
            requested_targets=("opencode",),
            existing_files={Path(".opencode/skills/sqlbuild/SKILL.md"): "custom instructions\n"},
            force=True,
            expected_written_paths=(Path(".opencode/skills/sqlbuild/SKILL.md"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_skill_update_options_when_updating_then_writes_expected_targets(
    test_case: SkillUpdateTestCase,
    tmp_path: Path,
) -> None:
    prepare_skill_update_project(
        project_dir=tmp_path,
        project_config=test_case.project_config,
        existing_files=test_case.existing_files,
    )

    result: SkillUpdateResult = update_sqlbuild_skills(
        project_dir=tmp_path,
        requested_targets=test_case.requested_targets,
        global_install=test_case.global_install,
        force=test_case.force,
        home_dir=tmp_path / "home",
    )

    assert result.written_paths == tuple(
        tmp_path / path for path in test_case.expected_written_paths
    )
    expected_path: Path
    for expected_path in test_case.expected_written_paths:
        contents: str = read_relative_file(project_dir=tmp_path, relative_path=expected_path)
        assert contents.startswith("---\nname: sqlbuild\n")
        assert generated_marker in contents
        assert test_case.expected_content_fragment in contents


@pytest.mark.parametrize(
    "test_case",
    [
        SkillUpdateTestCase(
            description="writes global skill targets under home directory",
            requested_targets=("opencode", "agents"),
            global_install=True,
            expected_written_paths=(
                Path("home/.config/opencode/skills/sqlbuild/SKILL.md"),
                Path("home/.agents/skills/sqlbuild/SKILL.md"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_global_skill_update_when_updating_then_writes_under_home_directory(
    test_case: SkillUpdateTestCase,
    tmp_path: Path,
) -> None:
    home_dir: Path = tmp_path / "home"

    result: SkillUpdateResult = update_sqlbuild_skills(
        project_dir=tmp_path,
        requested_targets=test_case.requested_targets,
        global_install=test_case.global_install,
        force=test_case.force,
        home_dir=home_dir,
    )

    assert result.written_paths == tuple(
        tmp_path / path for path in test_case.expected_written_paths
    )
    expected_path: Path
    for expected_path in test_case.expected_written_paths:
        contents: str = read_relative_file(project_dir=tmp_path, relative_path=expected_path)
        assert contents.startswith("---\nname: sqlbuild\n")
        assert generated_marker in contents


@pytest.mark.parametrize(
    "test_case",
    [
        SkillUpdateErrorTestCase(
            description="rejects non generated existing skill file without force",
            existing_files={Path(".opencode/skills/sqlbuild/SKILL.md"): "custom instructions\n"},
            requested_targets=("opencode",),
            expected_error_fragment="refusing to overwrite non-generated skill file",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_non_generated_skill_file_when_updating_without_force_then_raises_user_error(
    test_case: SkillUpdateErrorTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(project_dir=tmp_path, files=test_case.existing_files)

    with pytest.raises(CliUserError) as exc_info:
        update_sqlbuild_skills(project_dir=tmp_path, requested_targets=test_case.requested_targets)

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        SkillUpdateTestCase(
            description="keeps skill frontmatter before generated marker",
            expected_content_fragment=(
                f"---\nname: sqlbuild\n---\n\n{generated_marker}\n# SQLBuild Skill"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_skill_frontmatter_when_adding_generated_marker_then_marker_follows_frontmatter(
    test_case: SkillUpdateTestCase,
) -> None:
    content: str = "---\nname: sqlbuild\n---\n# SQLBuild Skill\n"

    updated_content: str = ensure_generated_marker(content)

    assert updated_content.startswith("---\nname: sqlbuild\n")
    assert test_case.expected_content_fragment in updated_content
