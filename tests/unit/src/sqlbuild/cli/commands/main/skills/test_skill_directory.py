from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

import pytest

from sqlbuild.cli.commands._helpers.skills.update import (
    generated_marker,
    load_packaged_skill_files,
    maintain_sqlbuild_skills,
    skill_entry_file,
    update_sqlbuild_skills,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.cli.output.models import SkillMaintenanceResult
from tests.unit.src.sqlbuild.cli.commands.main.skills._test_types import (
    SkillContentTestCase,
    SkillDirectoryCollisionTestCase,
    SkillDirectoryInstallTestCase,
    SkillDirectoryMaintenanceTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.skills.helpers import (
    install_packaged_skill,
    installed_skill_files,
    mentioned_sqb_commands,
    relative_markdown_links,
    write_project_files,
)

_SKILL_DIR: Path = Path(".agents/skills/sqlbuild")


@pytest.mark.parametrize(
    "test_case",
    [
        SkillDirectoryInstallTestCase(
            description="installs bundled guides and docs pages alongside SKILL.md",
        ),
        SkillDirectoryInstallTestCase(
            description="removes generated files that are no longer shipped",
            existing_files={
                _SKILL_DIR / "references/docs/retired_page.md": f"{generated_marker}\nold\n",
            },
            expected_absent_paths=(_SKILL_DIR / "references/docs/retired_page.md",),
        ),
        SkillDirectoryInstallTestCase(
            description="keeps user files that SQLBuild did not generate",
            existing_files={_SKILL_DIR / "references/team-notes.md": "our conventions\n"},
            expected_preserved_files={_SKILL_DIR / "references/team-notes.md": "our conventions\n"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_skill_directory_when_updating_then_it_matches_the_package(
    test_case: SkillDirectoryInstallTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(project_dir=tmp_path, files=test_case.existing_files)

    skill_dir: Path = install_packaged_skill(project_dir=tmp_path, target="agents")

    installed: dict[str, str] = installed_skill_files(skill_dir=skill_dir)
    packaged: dict[str, str] = load_packaged_skill_files()
    assert {path: installed[path] for path in packaged} == packaged
    assert "references/docs/CONTENTS.md" in packaged
    assert not any((tmp_path / path).exists() for path in test_case.expected_absent_paths)
    assert {
        path: (tmp_path / path).read_text(encoding="utf-8")
        for path in test_case.expected_preserved_files
    } == test_case.expected_preserved_files


@pytest.mark.parametrize(
    "test_case",
    [
        SkillDirectoryCollisionTestCase(
            description="custom reference file blocks the whole install",
            existing_files={_SKILL_DIR / "references/testing.md": "custom testing notes\n"},
            expected_error_fragment="references/testing.md",
            expected_unwritten_path=_SKILL_DIR / skill_entry_file,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_custom_file_in_skill_directory_when_updating_then_nothing_is_written(
    test_case: SkillDirectoryCollisionTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(project_dir=tmp_path, files=test_case.existing_files)

    with pytest.raises(CliUserError, match=test_case.expected_error_fragment):
        update_sqlbuild_skills(project_dir=tmp_path, requested_targets=("agents",))

    assert not (tmp_path / test_case.expected_unwritten_path).exists()
    assert {
        path: (tmp_path / path).read_text(encoding="utf-8") for path in test_case.existing_files
    } == test_case.existing_files


@pytest.mark.parametrize(
    "test_case",
    [
        SkillDirectoryMaintenanceTestCase(
            description="stale bundled page is reported",
            project_config='name = "demo"\nadapter = "duckdb"\n\n[skills]\ntargets = ["agents"]\n',
            stale_relative_path="references/docs/CONTENTS.md",
            expected_message_fragment="SQLBuild skill files are out of date",
            expected_restored=False,
        ),
        SkillDirectoryMaintenanceTestCase(
            description="stale bundled page is restored with auto update",
            project_config=(
                'name = "demo"\nadapter = "duckdb"\n\n[skills]\n'
                'targets = ["agents"]\nauto_update = true\n'
            ),
            stale_relative_path="references/docs/CONTENTS.md",
            expected_message_fragment="Updated stale SQLBuild skill files",
            expected_restored=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stale_reference_page_when_maintaining_then_directory_is_checked(
    test_case: SkillDirectoryMaintenanceTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(
        project_dir=tmp_path, files={Path("sqlbuild_project.toml"): test_case.project_config}
    )
    skill_dir: Path = install_packaged_skill(project_dir=tmp_path, target="agents")
    stale_path: Path = skill_dir / test_case.stale_relative_path
    stale_path.write_text(f"{generated_marker}\nold\n", encoding="utf-8")

    result: SkillMaintenanceResult = maintain_sqlbuild_skills(project_dir=tmp_path)

    assert test_case.expected_message_fragment in result.message
    assert (
        stale_path.read_text(encoding="utf-8")
        == load_packaged_skill_files()[test_case.stale_relative_path]
    ) is test_case.expected_restored


@pytest.mark.parametrize(
    "test_case",
    [
        SkillContentTestCase(
            description="entry stays short and every link and command resolves",
            max_entry_lines=500,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_packaged_skill_when_reading_then_entry_is_short_and_references_resolve(
    test_case: SkillContentTestCase,
) -> None:
    packaged: dict[str, str] = load_packaged_skill_files()
    authored_paths: set[str] = set(packaged) - set(fnmatch.filter(packaged, "references/docs/*"))
    authored: dict[str, str] = {path: packaged[path] for path in authored_paths}

    links: frozenset[str] = frozenset().union(
        *(
            relative_markdown_links(text=text, base=str(PurePosixPath(path).parent))
            for path, text in authored.items()
        )
    )
    commands: frozenset[str] = frozenset().union(
        *(mentioned_sqb_commands(text=text) for text in authored.values())
    )

    assert packaged[skill_entry_file].count("\n") <= test_case.max_entry_lines
    assert len({path.casefold() for path in packaged}) == len(packaged)
    assert links - packaged.keys() == test_case.expected_broken_links
    assert commands - {command.value for command in CliCommand} == (
        test_case.expected_unknown_commands
    )
