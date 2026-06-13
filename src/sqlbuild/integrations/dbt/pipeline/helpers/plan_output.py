"""SQLBuild plan output helpers for dbt interop pipelines."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.display_plan import build_display_only_sqlbuild_plan
from sqlbuild.compiler.planner.main.execution import build_execution_plan
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.compiler.planner.types import StandardScopePruning
from sqlbuild.integrations.dbt.main.profile_connection import resolve_raw_dbt_profile_connection
from sqlbuild.integrations.dbt.models import DbtCommandResult, NormalizedDbtProfileConnection


def dbt_failure_detail(result: DbtCommandResult) -> str | None:
    detail: str = (result.stderr or result.stdout).strip()
    return detail or None


def build_sqlbuild_plan_output(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    project: CompiledProject,
    adapter: BaseAdapter,
    adapter_name: str,
    selected_model_names: tuple[str, ...],
    required_dbt_unique_ids: tuple[str, ...],
    sqlbuild_args: tuple[str, ...],
    on_progress: Callable[[str], None] | None,
    on_connection_start: Callable[[int], None] | None,
    on_connection_complete: Callable[[int, float], None] | None,
    on_connection_error: Callable[[int, float], None] | None,
    deferred_relations: dict[str, RelationInfo] | None = None,
) -> PlanOutput | None:
    del required_dbt_unique_ids
    if not selected_model_names:
        return None
    cursor_overrides: CursorOverrides = _parse_cursor_overrides(sqlbuild_args)
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.monotonic() - start)
    try:
        try:
            return build_execution_plan(
                project=project,
                adapter=adapter,
                connection=connection,
                select=selected_model_names,
                cursor_overrides=cursor_overrides,
                full_refresh="--full-refresh" in sqlbuild_args,
                standard_scope_pruning=(
                    StandardScopePruning.PRUNE_UNCHANGED
                    if "--force" not in sqlbuild_args
                    else StandardScopePruning.NONE
                ),
                on_progress=on_progress,
                deferred_relations=deferred_relations,
            )
        except PlannerInputError:
            return build_display_only_sqlbuild_plan(
                project=project,
                selected_model_names=selected_model_names,
                full_refresh="--full-refresh" in sqlbuild_args,
            )
    finally:
        adapter.close(connection)


def _parse_cursor_overrides(args: tuple[str, ...]) -> CursorOverrides:
    return CursorOverrides(
        start_ts=_parse_value(args, "--start-cursor-ts"),
        end_ts=_parse_value(args, "--end-cursor-ts"),
        start_int=_parse_value(args, "--start-cursor-int"),
        end_int=_parse_value(args, "--end-cursor-int"),
    )


def resolve_connection_config(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
    adapter_name: str,
    discovered_inputs: DiscoveredProjectInputs,
) -> dict[str, object]:
    """Resolve dbt interop connection config without importing CLI helpers."""

    config: dict[str, object] = dict(raw_config)
    resolved_dbt_profile: NormalizedDbtProfileConnection | None = (
        resolve_raw_dbt_profile_connection(
            raw_config=config,
            project_dir=project_dir,
            adapter_name=adapter_name,
            project_config=discovered_inputs.project_config,
        )
    )
    if resolved_dbt_profile is not None:
        for warning in resolved_dbt_profile.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        config = resolved_dbt_profile.connection
    database: object | None = config.get("database")
    if (
        adapter_name == BuiltinAdapter.DUCKDB
        and isinstance(database, str)
        and not Path(database).is_absolute()
        and database != ":memory:"
    ):
        config["database"] = str(project_dir / database)
    return config


def _parse_value(args: tuple[str, ...], flag: str) -> str | None:
    if flag not in args:
        return None
    index: int = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]
