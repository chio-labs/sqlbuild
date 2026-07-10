"""Playground completion output rendering phase."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.playground.models import (
    PlaygroundCommandRequest,
    PlaygroundTarget,
)
from sqlbuild.cli.commands.helpers.playground.types import PlaygroundTemplate
from sqlbuild.shared.classes.cli_document import CliDocument
from sqlbuild.shared.helpers.output.cli_style import CliStyle
from sqlbuild.shared.helpers.output.colors import supports_color


def render_playground_completion_text(
    *,
    request: PlaygroundCommandRequest,
    target: PlaygroundTarget,
) -> str:
    """Render the playground creation summary and suggested commands."""

    display_path: str = str(request.target_path)
    style: CliStyle = CliStyle(use_color=supports_color())
    doc: CliDocument = CliDocument(style)
    doc.header("SQLBuild playground created")
    doc.blank()
    doc.field("Project", value=display_path)
    doc.field("Adapter", value="DuckDB")
    doc.field("Example", value=_example_name(target.template))
    doc.blank()
    doc.title_section("Try")
    doc.commands(
        _suggested_commands(template=target.template, display_path=display_path),
        style_command=False,
    )
    return doc.render()


def _suggested_commands(*, template: PlaygroundTemplate, display_path: str) -> tuple[str, ...]:
    commands: list[str] = [f"cd {display_path}"]
    if template == PlaygroundTemplate.VIRTUAL:
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
    elif template == PlaygroundTemplate.PYTHON_NODES:
        commands.extend(
            [
                "sqb plan --select +fact_orders --select +orders_export",
                "sqb build --select +fact_orders --select +orders_export",
                "sqb check --select check_orders_export",
            ]
        )
    elif template == PlaygroundTemplate.DBT:
        commands.extend(
            [
                "sqb dbt init --project-dir dbt_project --profiles-dir profiles",
                "sqb dbt build",
                "sqb dbt build",
            ]
        )
    else:
        commands.extend(["sqb compile", "sqb build", "sqb test", "sqb audit"])
    if template == PlaygroundTemplate.DAGSTER:
        commands.append("DAGSTER_IS_DEV_CLI=1 dagster dev -f dagster/definitions.py")
    if template == PlaygroundTemplate.RIVERS:
        commands.append("rivers dev rivers_pipeline.definitions")
    return tuple(commands)


def _example_name(template: PlaygroundTemplate) -> str:
    labels: dict[PlaygroundTemplate, str] = {
        PlaygroundTemplate.DAGSTER: "waffle shop + Dagster",
        PlaygroundTemplate.RIVERS: "waffle shop + Rivers",
        PlaygroundTemplate.VIRTUAL: "virtual environments waffle shop",
        PlaygroundTemplate.LOADER_WAFFLE_SHOP: "loader-focused waffle shop",
        PlaygroundTemplate.PYTHON_NODES: "Python nodes demo",
        PlaygroundTemplate.DBT: "dbt change-aware build, clone, and diff demo",
    }
    return labels.get(template, "waffle shop")
