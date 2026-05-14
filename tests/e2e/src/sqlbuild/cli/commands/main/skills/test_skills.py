from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entry import main
from sqlbuild.cli.commands.main.helpers.skills.update import generated_marker
from tests.e2e.src.sqlbuild.cli.commands.main.skills._test_types import (
    SkillsCliOverwriteTestCase,
    SkillsCliTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.skills.helpers import (
    existing_file_paths,
    write_existing_skill_file,
)

SKILLS_CLI_TEST_CASES: list[SkillsCliTestCase] = [
    SkillsCliTestCase(
        description="updates all local skill targets by default",
        argv=["skills", "update"],
        expected_exit_code=0,
        expected_files=(
            Path(".opencode/skills/sqlbuild/SKILL.md"),
            Path(".claude/skills/sqlbuild/SKILL.md"),
            Path(".agents/skills/sqlbuild/SKILL.md"),
        ),
    ),
    SkillsCliTestCase(
        description="updates only requested local skill target",
        argv=["skills", "update", "--target", "opencode"],
        expected_exit_code=0,
        expected_files=(Path(".opencode/skills/sqlbuild/SKILL.md"),),
        unexpected_files=(
            Path(".claude/skills/sqlbuild/SKILL.md"),
            Path(".agents/skills/sqlbuild/SKILL.md"),
        ),
    ),
]

SKILLS_CLI_OVERWRITE_TEST_CASES: list[SkillsCliOverwriteTestCase] = [
    SkillsCliOverwriteTestCase(
        description="refuses to overwrite custom skill file without force",
        argv=["skills", "update", "--target", "opencode"],
        existing_file=Path(".opencode/skills/sqlbuild/SKILL.md"),
        existing_content="custom project instructions\n",
        expected_exit_code=1,
        expected_content_fragment="custom project instructions",
    ),
    SkillsCliOverwriteTestCase(
        description="overwrites custom skill file with force",
        argv=["skills", "update", "--target", "opencode", "--force"],
        existing_file=Path(".opencode/skills/sqlbuild/SKILL.md"),
        existing_content="custom project instructions\n",
        expected_exit_code=0,
        expected_content_fragment="# SQLBuild Skill",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SKILLS_CLI_TEST_CASES,
    ids=[case.description for case in SKILLS_CLI_TEST_CASES],
)
def test_given_skills_update_cli_when_running_then_writes_expected_skill_files(
    test_case: SkillsCliTestCase,
    tmp_path: Path,
) -> None:
    exit_code: int = main(["--project-dir", str(tmp_path), *test_case.argv])

    assert exit_code == test_case.expected_exit_code
    assert existing_file_paths(project_dir=tmp_path, relative_paths=test_case.expected_files) == (
        test_case.expected_files
    )
    expected_file: Path
    for expected_file in test_case.expected_files:
        contents: str = (tmp_path / expected_file).read_text(encoding="utf-8")
        assert generated_marker in contents
        assert test_case.expected_content_fragment in contents
    assert (
        existing_file_paths(project_dir=tmp_path, relative_paths=test_case.unexpected_files) == ()
    )


@pytest.mark.parametrize(
    "test_case",
    SKILLS_CLI_OVERWRITE_TEST_CASES,
    ids=[case.description for case in SKILLS_CLI_OVERWRITE_TEST_CASES],
)
def test_given_existing_custom_skill_when_running_update_then_force_controls_overwrite(
    test_case: SkillsCliOverwriteTestCase,
    tmp_path: Path,
) -> None:
    write_existing_skill_file(
        project_dir=tmp_path,
        relative_path=test_case.existing_file,
        contents=test_case.existing_content,
    )

    exit_code: int = main(["--project-dir", str(tmp_path), *test_case.argv])

    contents: str = (tmp_path / test_case.existing_file).read_text(encoding="utf-8")
    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_content_fragment in contents
