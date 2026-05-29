"""Create a local SQLBuild playground project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.playground.copy import create_playground_project
from sqlbuild.cli.commands.main.helpers.skills.update import update_sqlbuild_skills
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.colors import supports_color


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
    style: CliStyle = CliStyle(use_color=use_color)
    heading: str = style.title("SQLBuild playground created")
    project_label: str = style.value("Project")
    adapter_label: str = style.value("Adapter")
    example_label: str = style.value("Example")
    try_label: str = style.title("Try")
    command_prefix: str = style.command("  ")

    print(heading)
    print()
    print(f"  {project_label}: {display_path}")
    print(f"  {adapter_label}: DuckDB")
    example_name: str = (
        "waffle shop + Dagster"
        if template == "dagster"
        else "waffle shop + Rivers"
        if template == "rivers"
        else "virtual environments waffle shop"
        if template == "virtual"
        else "loader-focused waffle shop"
        if template == "loader_waffle_shop"
        else "waffle shop"
    )
    print(f"  {example_label}: {example_name}")
    print()
    print(f"{try_label}:")
    print(f"{command_prefix}cd {display_path}")
    if template == "virtual":
        print(f"{command_prefix}sqb state init")
        print(f"{command_prefix}sqb build")
        print(f"{command_prefix}sqb build --virtual-env pr")
        print(f"{command_prefix}sqb test")
        print(f"{command_prefix}sqb audit")
        print(f"{command_prefix}sqb scenario test")
        print(f"{command_prefix}sqb diff dev:pr --schema-only")
        print(f"{command_prefix}sqb promote --from pr --to dev")
    else:
        print(f"{command_prefix}sqb compile")
        print(f"{command_prefix}sqb build")
        print(f"{command_prefix}sqb test")
        print(f"{command_prefix}sqb audit")
    if template == "dagster":
        print(f"{command_prefix}DAGSTER_IS_DEV_CLI=1 dagster dev -f dagster/definitions.py")
    if template == "rivers":
        print(f"{command_prefix}rivers dev rivers_pipeline.definitions")
    return 0
