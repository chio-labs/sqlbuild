"""CLI dbt interop command entry points."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.integrations.dbt.models import DbtInteropPlan
from sqlbuild.integrations.dbt.pipeline.main.plan import plan_dbt_interop_from_project
from sqlbuild.integrations.dbt.pipeline.main.render_plan import (
    render_dbt_interop_plan,
)
from sqlbuild.shared.helpers.colors import supports_color


def run_dbt_plan(
    project_dir: Path | None,
    args: tuple[str, ...],
    no_color: bool = False,
) -> int:
    """Execute `sqb dbt plan`."""

    json_output: bool = "--json" in args
    routed_args: tuple[str, ...] = tuple(arg for arg in args if arg != "--json")
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    plan: DbtInteropPlan = plan_dbt_interop_from_project(
        project_dir=effective_project_dir,
        args=routed_args,
    )
    use_color: bool = not no_color and supports_color()
    print(render_dbt_interop_plan(plan, json_output=json_output, use_color=use_color))
    return 0
