"""Create a local SQLBuild playground project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.playground.copy import create_playground_project
from sqlbuild.cli.commands.main.helpers.playground.types import PlaygroundTemplate
from sqlbuild.cli.commands.main.helpers.skills.update import update_sqlbuild_skills
from sqlbuild.shared.helpers.cli_document import CliDocument
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.colors import supports_color


def run_playground(
    project_dir: Path | None,
    target_path: str,
    template: str = PlaygroundTemplate.WAFFLE_SHOP.value,
) -> int:
    """Create a self-contained waffle shop playground project."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    target_dir: Path = Path(target_path)
    if not target_dir.is_absolute():
        target_dir = base_dir / target_dir

    resolved_template: PlaygroundTemplate = PlaygroundTemplate(template)
    create_playground_project(target_dir=target_dir, template=resolved_template.value)
    if resolved_template != PlaygroundTemplate.DBT:
        update_sqlbuild_skills(project_dir=target_dir)
    display_path: str = str(target_path)
    use_color: bool = supports_color()
    style: CliStyle = CliStyle(use_color=use_color)
    example_name: str = _example_name(resolved_template)
    doc: CliDocument = CliDocument(style)
    doc.header("SQLBuild playground created")
    doc.blank()
    doc.field("Project", display_path)
    doc.field("Adapter", "DuckDB")
    doc.field("Example", example_name)
    doc.blank()
    doc.title_section("Try")
    commands: list[str] = [f"cd {display_path}"]
    if resolved_template == PlaygroundTemplate.VIRTUAL:
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
    elif resolved_template == PlaygroundTemplate.PYTHON_NODES:
        commands.extend(
            [
                "sqb plan --select +fact_orders --select +orders_export",
                "sqb build --select +fact_orders --select +orders_export",
                "sqb check --select check_orders_export",
            ]
        )
    elif resolved_template == PlaygroundTemplate.DBT:
        commands.extend(
            [
                "sqb dbt init --project-dir dbt_project --profiles-dir profiles",
                "sqb dbt build",
                "sqb dbt build",
            ]
        )
    else:
        commands.extend(["sqb compile", "sqb build", "sqb test", "sqb audit"])
    if resolved_template == PlaygroundTemplate.DAGSTER:
        commands.append("DAGSTER_IS_DEV_CLI=1 dagster dev -f dagster/definitions.py")
    if resolved_template == PlaygroundTemplate.RIVERS:
        commands.append("rivers dev rivers_pipeline.definitions")
    doc.commands(tuple(commands), style_command=False)
    print(doc.render(), end="")
    return 0


def _example_name(template: PlaygroundTemplate) -> str:
    labels: dict[PlaygroundTemplate, str] = {
        PlaygroundTemplate.DAGSTER: "waffle shop + Dagster",
        PlaygroundTemplate.RIVERS: "waffle shop + Rivers",
        PlaygroundTemplate.VIRTUAL: "virtual environments waffle shop",
        PlaygroundTemplate.LOADER_WAFFLE_SHOP: "loader-focused waffle shop",
        PlaygroundTemplate.PYTHON_NODES: "Python nodes demo",
        PlaygroundTemplate.DBT: "dbt reuse demo",
    }
    return labels.get(template, "waffle shop")
