"""SQLBuild plan output helpers for dbt interop pipelines."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.display_plan import build_display_only_sqlbuild_plan
from sqlbuild.compiler.planner.main.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    CursorOverrides,
    DependencyBaselinePlanEntry,
    PlanOutput,
)
from sqlbuild.compiler.planner.types import StandardScopePruning
from sqlbuild.integrations.dbt.helpers.manifest import resolve_dbt_manifest_model
from sqlbuild.integrations.dbt.helpers.model_planning import build_dbt_model_planning_result
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCommandResult,
    DbtModelPlanningResult,
)
from sqlbuild.integrations.dbt.shared.helpers.connection import resolve_connection_config
from sqlbuild.shared.types import SqlReferenceKind


def dbt_failure_detail(result: DbtCommandResult) -> str | None:
    detail: str = (result.stderr or result.stdout).strip()
    return detail or None


def find_sqlbuild_models_with_missing_dbt_relations(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    adapter: BaseAdapter,
    connection: object,
    selected_model_names: tuple[str, ...],
    dbt_unique_ids_selected_for_execution: frozenset[str],
) -> dict[str, tuple[DbtManifestModel, ...]]:
    """Return selected SQLBuild models blocked by absent, unselected dbt refs."""

    selected_names: frozenset[str] = frozenset(selected_model_names)
    blocked: dict[str, list[DbtManifestModel]] = {}
    for model in project.models:
        if model.name not in selected_names:
            continue
        for reference in model.references:
            if reference.ref_kind != SqlReferenceKind.DBT_REF:
                continue
            dbt_model: DbtManifestModel = resolve_dbt_manifest_model(
                manifest=manifest,
                package_name=reference.ref_package,
                name=reference.ref_name,
            )
            if dbt_model.unique_id in dbt_unique_ids_selected_for_execution:
                continue
            if adapter.relation_exists(
                connection,
                database=dbt_model.database,
                schema=dbt_model.schema,
                name=dbt_model.alias or dbt_model.name,
            ):
                continue
            blocked.setdefault(model.name, []).append(dbt_model)
    return {name: tuple(models) for name, models in blocked.items()}


def find_direct_dbt_dependency_unique_ids(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    selected_model_names: tuple[str, ...],
) -> tuple[str, ...]:
    """Return direct dbt refs needed by selected SQLBuild models."""

    selected_names: frozenset[str] = frozenset(selected_model_names)
    unique_ids: set[str] = set()
    for model in project.models:
        if model.name not in selected_names:
            continue
        for reference in model.references:
            if reference.ref_kind != SqlReferenceKind.DBT_REF:
                continue
            dbt_model: DbtManifestModel = resolve_dbt_manifest_model(
                manifest=manifest,
                package_name=reference.ref_package,
                name=reference.ref_name,
            )
            unique_ids.add(dbt_model.unique_id)
    return tuple(sorted(unique_ids))


def build_sqlbuild_plan_output(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    project: CompiledProject,
    adapter: BaseAdapter,
    adapter_name: str,
    selected_model_names: tuple[str, ...],
    required_dbt_unique_ids: tuple[str, ...],
    forced_stale_model_names: tuple[str, ...] = (),
    external_blocked_model_names: tuple[str, ...] = (),
    sqlbuild_args: tuple[str, ...],
    on_progress: Callable[[str], None] | None,
    on_connection_start: Callable[[int], None] | None,
    on_connection_complete: Callable[[int, float], None] | None,
    on_connection_error: Callable[[int, float], None] | None,
    deferred_relations: dict[str, RelationInfo] | None = None,
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = (),
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
            plan_output: PlanOutput = build_execution_plan(
                project=project,
                adapter=adapter,
                connection=connection,
                select=selected_model_names,
                cursor_overrides=cursor_overrides,
                full_refresh="--full-refresh" in sqlbuild_args,
                forced_stale_model_names=forced_stale_model_names,
                external_blocked_model_names=external_blocked_model_names,
                standard_scope_pruning=(
                    StandardScopePruning.PRUNE_UNCHANGED
                    if "--force" not in sqlbuild_args
                    else StandardScopePruning.NONE
                ),
                on_progress=on_progress,
                deferred_relations=deferred_relations,
            )
            return replace(
                plan_output,
                dependency_baseline_entries=(
                    *dependency_baseline_entries,
                    *plan_output.dependency_baseline_entries,
                ),
            )
        except PlannerInputError:
            return build_display_only_sqlbuild_plan(
                project=project,
                selected_model_names=selected_model_names,
                full_refresh="--full-refresh" in sqlbuild_args,
            )
    finally:
        adapter.close(connection)


def build_dbt_model_plan_output(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    project: CompiledProject,
    adapter: BaseAdapter,
    adapter_name: str,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph | None = None,
    candidate_unique_ids: tuple[str, ...],
    full_refresh: bool = False,
    on_connection_start: Callable[[int], None] | None,
    on_connection_complete: Callable[[int, float], None] | None,
    on_connection_error: Callable[[int, float], None] | None,
) -> DbtModelPlanningResult | None:
    if not candidate_unique_ids:
        return None
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
        return build_dbt_model_planning_result(
            manifest=manifest,
            candidate_unique_ids=candidate_unique_ids,
            project=project,
            graph=graph,
            full_refresh=full_refresh,
            adapter=adapter,
            connection=connection,
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


def _parse_value(args: tuple[str, ...], flag: str) -> str | None:
    if flag not in args:
        return None
    index: int = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]
