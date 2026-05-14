"""Install or update SQLBuild agent skills."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.skills.models import SkillUpdateResult
from sqlbuild.cli.commands.main.helpers.skills.update import update_sqlbuild_skills


def run_skills_update(
    project_dir: Path | None,
    global_install: bool = False,
    targets: tuple[str, ...] = (),
    force: bool = False,
) -> int:
    """Install or update SQLBuild skill files."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    result: SkillUpdateResult = update_sqlbuild_skills(
        project_dir=base_dir,
        global_install=global_install,
        requested_targets=targets,
        force=force,
    )
    print("Updated SQLBuild skill files:")
    for written_path in result.written_paths:
        print(f"  {written_path}")
    return 0
