"""Create a local SQLBuild playground project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.playground.copy import create_playground_project
from sqlbuild.cli.commands.main.helpers.skills.update import update_sqlbuild_skills
from sqlbuild.shared.helpers.cli_document import CliDocument
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
    doc: CliDocument = CliDocument(style)
    doc.header("SQLBuild playground created")
    doc.blank()
    doc.field("Project", display_path)
    doc.field("Adapter", "DuckDB")
    doc.field("Example", example_name)
    doc.blank()
    doc.title_section("Try")
    commands: list[str] = [f"cd {display_path}"]
    if template == "virtual":
        commands.extend(
            [
                "sqb state init",
                "sqb build",
                "sqb build --virtual-env pr",
                "sqb test",
                "sqb audit",
                "sqb scenario test",
                "sqb diff dev:pr --schema-only",
                "sqb promote --from pr --to dev",
            ]
        )
    else:
        commands.extend(["sqb compile", "sqb build", "sqb test", "sqb audit"])
    if template == "dagster":
        commands.append("DAGSTER_IS_DEV_CLI=1 dagster dev -f dagster/definitions.py")
    if template == "rivers":
        commands.append("rivers dev rivers_pipeline.definitions")
    doc.commands(tuple(commands), style_command=False)
    print(doc.render(), end="")
    return 0
