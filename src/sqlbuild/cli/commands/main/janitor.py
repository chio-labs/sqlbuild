"""CLI janitor command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.janitor.output import (
    confirmation_text,
    environment_label,
    write_disabled,
    write_plan,
)
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_connection_config
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.project import compile_project
from sqlbuild.executor.janitor.main.execute import execute_janitor_plan
from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import JanitorExecutionResult, JanitorPlan
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_janitor(
    project_dir: Path | None,
    no_color: bool = False,
    auto_approve: bool = False,
    retention_days: int | None = None,
) -> int:
    """Execute the janitor command."""

    del no_color
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    if not discovered_inputs.project_config.janitor.enabled:
        write_disabled(sys.stdout)
        return 0
    effective_retention_days: int = (
        retention_days
        if retention_days is not None
        else discovered_inputs.project_config.janitor.retention_days
    )
    if effective_retention_days < 0:
        raise CliUserError("janitor --retention-days must be >= 0")

    effective_adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        effective_adapter_name, project_dir=effective_project_dir
    )
    project: CompiledProject = compile_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
    )
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=project.effective_connection,
        project_dir=effective_project_dir,
        adapter_name=effective_adapter_name,
    )
    connection: object = adapter.connect(connection_config)
    try:
        plan: JanitorPlan = build_janitor_plan(
            project=project,
            adapter=adapter,
            connection=connection,
            retention_days=effective_retention_days,
            delete_tracked_only=discovered_inputs.project_config.janitor.delete_tracked_only,
            exclude_patterns=discovered_inputs.project_config.janitor.exclude_patterns,
        )
        write_plan(plan=plan, stream=sys.stdout)
        if not plan.candidates:
            return 0
        if not auto_approve and not _confirm(plan=plan):
            sys.stdout.write("Janitor cancelled.\n")
            return 1
        result: JanitorExecutionResult = execute_janitor_plan(
            plan=plan,
            adapter=adapter,
            connection=connection,
        )
        sys.stdout.write(f"Deleted {len(result.deleted)} objects.\n")
        return 0
    finally:
        adapter.close(connection)


def _confirm(*, plan: JanitorPlan) -> bool:
    expected: str = confirmation_text(plan)
    sys.stdout.write(
        f"Janitor will delete {len(plan.candidates)} objects from {environment_label(plan)}.\n"
    )
    if plan.retention_days == 0:
        sys.stdout.write("Retention: disabled (0 days)\n")
        sys.stdout.write("Age metadata will not be checked.\n")
    else:
        sys.stdout.write(f"Retention: {plan.retention_days} days\n")
    sys.stdout.write(f"\nType `{expected}` to continue: ")
    sys.stdout.flush()
    response: str = input()
    return response == expected
