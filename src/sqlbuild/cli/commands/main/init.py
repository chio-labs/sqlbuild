"""Scaffold a new blank SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.init.scaffold import scaffold_blank_project
from sqlbuild.cli.commands.main.helpers.skills.update import update_sqlbuild_skills
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.colors import supports_color


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
    style: CliStyle = CliStyle(use_color=use_color)
    heading: str = style.title("SQLBuild project created")
    project_label: str = style.value("Project")
    config_label: str = style.value("Config")
    next_steps_label: str = style.section("Next steps")
    print(heading)
    print()
    print(f"  {project_label}: {project_name}")
    print(f"  {config_label}:  sqlbuild_project.toml")
    print()
    print(f"{next_steps_label}:")
    print("  1. Add sources to sources/")
    print("  2. Add seeds to seeds/ or loaders to loaders/")
    print("  3. Add functions to functions/ or macros to macros/")
    print("  4. Add models to models/staging/ and models/marts/")
    print("  5. Add tests to tests/unit/ or tests/scenarios/")
    print(f"  6. {style.command('sqb compile')}")
    print(f"  7. {style.command('sqb build')}")
    return 0
