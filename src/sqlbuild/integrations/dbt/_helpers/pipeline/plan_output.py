"""Native SQLBuild plan output helpers for dbt interop pipelines."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.resolve_model_deferral_inputs import (
    resolve_model_deferral_inputs,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.execution.display_plan import build_display_only_sqlbuild_plan
from sqlbuild.compiler.planner.main.execution.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    CursorOverrides,
    DeferralInputs,
    PlannerOverrides,
    PlannerPolicies,
    PlannerSelection,
    PlanOutput,
)
from sqlbuild.integrations.dbt.constants import DBT_FULL_REFRESH_FLAG
from sqlbuild.integrations.dbt.main.profile._resolve_connection_config import (
    resolve_connection_config,
)
from sqlbuild.integrations.dbt.models import (
    DbtCommandResult,
    DbtInteropCompiledProject,
    DbtInteropPlan,
    DbtPlanEnvironment,
    DbtSqlbuildPlanRequest,
)
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback


def dbt_failure_detail(result: DbtCommandResult) -> str | None:
    detail: str = (result.stderr or result.stdout).strip()
    return detail or None


def build_sqlbuild_plan_output(
    *,
    environment: DbtPlanEnvironment,
    request: DbtSqlbuildPlanRequest,
    hooks: ConnectionHooks,
) -> PlanOutput | None:
    """Build a native SQLBuild plan for selected SQLBuild models."""

    if not request.selected_model_names:
        return None
    planning_project: CompiledProject = environment.project
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(
            discovered_inputs=environment.discovered_inputs
        ),
        project_dir=environment.project_dir,
        adapter_name=environment.adapter_name,
        discovered_inputs=environment.discovered_inputs,
    )
    connection: Any = _connect_for_plan(
        adapter=environment.adapter,
        connection_config=connection_config,
        hooks=hooks,
    )
    try:
        deferral: DeferralInputs = _build_deferral_inputs(
            environment=environment,
            request=request,
            connection=connection,
        )
        try:
            return build_execution_plan(
                project=planning_project,
                adapter=environment.adapter,
                connection=connection,
                selection=PlannerSelection(select=request.selected_model_names),
                overrides=PlannerOverrides(
                    cursor_overrides=_parse_cursor_overrides(request.sqlbuild_args),
                    full_refresh=DBT_FULL_REFRESH_FLAG in request.sqlbuild_args,
                    external_blocked_model_names=request.external_blocked_model_names,
                ),
                deferral=deferral,
                policies=PlannerPolicies(),
                on_progress=hooks.on_progress,
            )
        except PlannerInputError:
            return build_display_only_sqlbuild_plan(
                project=planning_project,
                selected_model_names=request.selected_model_names,
                full_refresh=DBT_FULL_REFRESH_FLAG in request.sqlbuild_args,
            )
    finally:
        environment.adapter.close(connection)


def attach_sqlbuild_plan_output(
    *,
    plan: DbtInteropPlan,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    compiled: DbtInteropCompiledProject,
    sqlbuild_args: tuple[str, ...],
    connection_progress: Any | None,
    on_progress: Callable[[str], None] | None,
) -> DbtInteropPlan:
    """Attach native SQLBuild planning only when SQLBuild work is selected."""

    sqlbuild_plan_output: PlanOutput | None = build_sqlbuild_plan_output(
        environment=DbtPlanEnvironment(
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
            project=compiled.project,
            adapter=compiled.adapter,
            adapter_name=compiled.adapter_name,
        ),
        request=DbtSqlbuildPlanRequest(
            selected_model_names=plan.selection.sqlbuild_model_names,
            sqlbuild_args=sqlbuild_args,
        ),
        hooks=_connection_progress_hooks(
            connection_progress=connection_progress,
            on_progress=on_progress,
        ),
    )
    if sqlbuild_plan_output is None:
        return plan
    return replace(plan, sqlbuild_plan_output=sqlbuild_plan_output)


def _connect_for_plan(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    hooks: ConnectionHooks,
) -> Any:
    if hooks.on_connection_start is not None:
        hooks.on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if hooks.on_connection_error is not None:
            hooks.on_connection_error(connection_count=1, elapsed_seconds=time.monotonic() - start)
        raise
    if hooks.on_connection_complete is not None:
        hooks.on_connection_complete(connection_count=1, elapsed_seconds=time.monotonic() - start)
    return connection


def _build_deferral_inputs(
    *,
    environment: DbtPlanEnvironment,
    request: DbtSqlbuildPlanRequest,
    connection: Any,
) -> DeferralInputs:
    defer_to: str | None = _parse_value(args=request.sqlbuild_args, flag="--defer-to")
    return resolve_model_deferral_inputs(
        project=environment.project,
        discovered_inputs=environment.discovered_inputs,
        adapter=environment.adapter,
        connection=connection,
        defer_to=defer_to,
    )


def _parse_cursor_overrides(args: tuple[str, ...]) -> CursorOverrides:
    return CursorOverrides(
        start_ts=_parse_value(args=args, flag="--start-cursor-ts"),
        end_ts=_parse_value(args=args, flag="--end-cursor-ts"),
        start_int=_parse_value(args=args, flag="--start-cursor-int"),
        end_int=_parse_value(args=args, flag="--end-cursor-int"),
    )


def _parse_value(*, args: tuple[str, ...], flag: str) -> str | None:
    if flag not in args:
        return None
    index: int = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]


def _connection_progress_hooks(
    *,
    connection_progress: Any | None,
    on_progress: Callable[[str], None] | None,
) -> ConnectionHooks:
    if connection_progress is None:
        return ConnectionHooks(on_progress=on_progress)
    on_connection_complete: ConnectionElapsedCallback = connection_progress.on_connection_complete
    on_connection_error: ConnectionElapsedCallback = connection_progress.on_connection_error
    return ConnectionHooks(
        on_progress=on_progress,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=on_connection_complete,
        on_connection_error=on_connection_error,
    )
