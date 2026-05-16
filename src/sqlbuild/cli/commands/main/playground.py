"""Create a local SQLBuild playground project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.playground.copy import create_playground_project
from sqlbuild.cli.commands.main.helpers.skills.update import update_sqlbuild_skills
from sqlbuild.shared.helpers.colors import blue_bold, dim, green_bold, supports_color


def run_playground(
    project_dir: Path | None, target_path: str, template: str = "waffle_shop"
) -> int:
    """Create a self-contained waffle shop playground project."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    target_dir: Path = Path(target_path)
    if not target_dir.is_absolute():
        target_dir = base_dir / target_dir

    create_playground_project(target_dir=target_dir, template=template)
    update_sqlbuild_skills(project_dir=target_dir)
    display_path: str = str(target_path)
    use_color: bool = supports_color()
    heading: str = (
        green_bold("SQLBuild playground created") if use_color else "SQLBuild playground created"
    )
    project_label: str = blue_bold("Project") if use_color else "Project"
    adapter_label: str = blue_bold("Adapter") if use_color else "Adapter"
    example_label: str = blue_bold("Example") if use_color else "Example"
    try_label: str = green_bold("Try") if use_color else "Try"
    command_prefix: str = dim("  ") if use_color else "  "

    print(heading)
    print()
    print(f"  {project_label}: {display_path}")
    print(f"  {adapter_label}: DuckDB")
    print(
        f"  {example_label}: {'waffle shop + Dagster' if template == 'dagster' else 'waffle shop'}"
    )
    print()
    print(f"{try_label}:")
    print(f"{command_prefix}cd {display_path}")
    print(f"{command_prefix}sqb compile")
    print(f"{command_prefix}sqb build")
    print(f"{command_prefix}sqb test")
    print(f"{command_prefix}sqb audit")
    if template == "dagster":
        print(f"{command_prefix}DAGSTER_IS_DEV_CLI=1 dagster dev -f dagster/definitions.py")
    return 0
