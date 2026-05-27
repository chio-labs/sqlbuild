"""Scaffold a new blank SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.init.scaffold import scaffold_blank_project
from sqlbuild.cli.commands.main.helpers.skills.update import update_sqlbuild_skills
from sqlbuild.shared.helpers.colors import green_bold, supports_color


def run_init(project_dir: Path | None) -> int:
    """Create a minimal SQLBuild project in the current directory."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    project_file: Path = base_dir / "sqlbuild_project.toml"

    if project_file.exists():
        from sqlbuild.cli.commands.main.shared.exceptions import CliUserError

        raise CliUserError(
            "sqlbuild_project.toml already exists in this directory",
            code="C900",
        )

    project_name: str = base_dir.name.replace("-", "_").replace(" ", "_").lower()

    scaffold_blank_project(base_dir=base_dir, project_name=project_name)

    update_sqlbuild_skills(project_dir=base_dir)

    use_color: bool = supports_color()
    heading: str = (
        green_bold("SQLBuild project created") if use_color else "SQLBuild project created"
    )
    print(heading)
    print()
    print(f"  Project: {project_name}")
    print("  Config:  sqlbuild_project.toml")
    print()
    print("Next steps:")
    print("  1. Add sources to sources/")
    print("  2. Add models to models/staging/ and models/marts/")
    print("  3. sqb compile")
    print("  4. sqb build")
    return 0
