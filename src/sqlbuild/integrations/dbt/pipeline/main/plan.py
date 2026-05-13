"""Runtime planning pipeline for `sqb dbt plan`."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredDbtManifestFile, DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.graph import build_downstream_deps, build_upstream_deps
from sqlbuild.compiler.planner.helpers.strategy import get_materialization_type
from sqlbuild.compiler.planner.main.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CursorOverrides,
    ModelPlanEntry,
    PlanOutput,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.integrations.dbt.exceptions import DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers.args import route_dbt_interop_args
from sqlbuild.integrations.dbt.helpers.graph import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest import load_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.plan_orchestration import plan_dbt_interop_command
from sqlbuild.integrations.dbt.helpers.plan_runtime import (
    resolve_dbt_interop_adapter,
    resolve_dbt_manifest_path,
    resolve_dbt_plan_options,
)
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandResult,
    DbtInteropPlan,
    DbtInteropRoutedArgs,
    DbtManifestIndex,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def plan_dbt_interop_from_project(
    *,
    project_dir: Path,
    args: tuple[str, ...],
    dbt_runner: DbtRunner | None = None,
    dbt_executable: str = "dbt",
    sqlbuild_executable: str = "sqb",
    no_sql_validation: bool = False,
    on_progress: Callable[[str], None] | None = None,
    progress_stream: TextIO | None = None,
    use_color: bool = False,
) -> DbtInteropPlan:
    """Build a dbt interop plan from real project files and dbt artifacts."""

    routed: DbtInteropRoutedArgs = route_dbt_interop_args(
        command=DbtInteropCommand.PLAN,
        args=args,
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    dbt_options: DbtCliOptions = resolve_dbt_plan_options(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        dbt_args=routed.dbt_args,
    )
    runner: DbtRunner = dbt_runner or DbtRunner(dbt_executable=dbt_executable)
    dbt_compile_start: float = time.monotonic()
    _report_progress(on_progress, "Compiling dbt project...")
    compile_result: DbtCommandResult = runner.compile(options=dbt_options)
    if compile_result.returncode != 0:
        raise DbtInteropRuntimeError(
            "dbt compile failed",
            help=_dbt_failure_detail(compile_result),
        )
    _report_progress(
        on_progress, f"Compiled dbt project. ({time.monotonic() - dbt_compile_start:.2f}s)"
    )
    manifest_start: float = time.monotonic()
    _report_progress(on_progress, "Loading dbt manifest...")
    manifest_path: Path = resolve_dbt_manifest_path(options=dbt_options)
    manifest: DbtManifestIndex = load_dbt_manifest_index(manifest_path=manifest_path)
    _report_progress(
        on_progress, f"Loaded dbt manifest. ({time.monotonic() - manifest_start:.2f}s)"
    )
    sqlbuild_compile_start: float = time.monotonic()
    _report_progress(on_progress, "Compiling SQLBuild project...")
    discovered_with_manifest: DiscoveredProjectInputs = replace(
        discovered_inputs,
        dbt_manifest_file=DiscoveredDbtManifestFile(
            file_path=manifest_path,
            relative_path=Path("manifest.json"),
            contents=manifest_path.read_text(encoding="utf-8"),
        ),
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_dbt_interop_adapter(adapter_name, project_dir=project_dir)
    connection_progress: ConnectionProgressReporter | None = (
        ConnectionProgressReporter(
            adapter_name=adapter_name,
            stream=progress_stream,
            use_color=use_color,
        )
        if progress_stream is not None
        else None
    )
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_with_manifest,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
    )
    _report_progress(
        on_progress,
        f"Compiled SQLBuild project. ({time.monotonic() - sqlbuild_compile_start:.2f}s)",
    )
    graph_start: float = time.monotonic()
    _report_progress(on_progress, "Building dbt interop graph...")
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    _report_progress(
        on_progress, f"Built dbt interop graph. ({time.monotonic() - graph_start:.2f}s)"
    )
    selection_start: float = time.monotonic()
    _report_progress(on_progress, "Resolving dbt and SQLBuild selection...")
    plan: DbtInteropPlan = plan_dbt_interop_command(
        command=DbtInteropCommand.PLAN,
        project=project,
        manifest=manifest,
        graph=graph,
        dbt_runner=runner,
        dbt_options=dbt_options,
        select=routed.select,
        exclude=routed.exclude,
        dbt_command_args=routed.dbt_args,
        sqlbuild_command_args=routed.sqlbuild_args,
        dbt_executable=dbt_executable,
        sqlbuild_executable=sqlbuild_executable,
    )
    sqlbuild_plan_output: PlanOutput | None = _build_sqlbuild_plan_output(
        project_dir=project_dir,
        discovered_inputs=discovered_with_manifest,
        project=project,
        adapter=adapter,
        adapter_name=adapter_name,
        selected_model_names=plan.selection.sqlbuild_model_names,
        required_dbt_unique_ids=plan.selection.dbt_required_unique_ids,
        sqlbuild_args=routed.sqlbuild_args,
        on_progress=on_progress,
        on_connection_start=(
            None if connection_progress is None else connection_progress.on_connection_start
        ),
        on_connection_complete=(
            None if connection_progress is None else connection_progress.on_connection_complete
        ),
        on_connection_error=(
            None if connection_progress is None else connection_progress.on_connection_error
        ),
    )
    if sqlbuild_plan_output is not None:
        plan = replace(plan, sqlbuild_plan_output=sqlbuild_plan_output)
    _report_progress(
        on_progress,
        f"Generated dbt interop plan. ({time.monotonic() - selection_start:.2f}s)",
    )
    return plan


def _report_progress(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)


def _dbt_failure_detail(result: DbtCommandResult) -> str | None:
    detail: str = (result.stderr or result.stdout).strip()
    return detail or None


def _build_sqlbuild_plan_output(
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
    if not selected_model_names:
        return None
    cursor_overrides: CursorOverrides = _parse_cursor_overrides(sqlbuild_args)
    connection_config: dict[str, object] = _resolve_connection_config(
        raw_config=build_effective_connection_config(discovered_inputs=discovered_inputs),
        project_dir=project_dir,
        adapter_name=adapter_name,
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
                on_progress=on_progress,
                deferred_relations=deferred_relations,
            )
        except PlannerInputError:
            return _build_display_only_sqlbuild_plan(
                project=project,
                selected_model_names=selected_model_names,
                full_refresh="--full-refresh" in sqlbuild_args,
            )
    finally:
        adapter.close(connection)


def _build_display_only_sqlbuild_plan(
    *, project: CompiledProject, selected_model_names: tuple[str, ...], full_refresh: bool
) -> PlanOutput:
    selected_names: frozenset[str] = frozenset(selected_model_names)
    model_entries: list[ModelPlanEntry] = []
    for model in project.models:
        if model.name not in selected_names:
            continue
        materialization_type: MaterializationType = get_materialization_type(model)
        model_entries.append(
            ModelPlanEntry(
                key=model.key,
                name=model.name,
                relative_path=model.relative_path,
                materialization_type=materialization_type,
                action=_display_action(materialization_type),
                reason=PlanReason.FULL_REFRESH if full_refresh else PlanReason.NO_CHANGE,
                target=model.target,
                fingerprint_query_sql=model.query_sql,
                resolved_sql=model.query_sql,
                logical_ddl="",
                incremental_strategy=_as_optional_string(
                    model.config.values.get("incremental_strategy")
                ),
                incremental_mode=_as_optional_string(model.config.values.get("incremental_mode")),
                cursor_column=_as_optional_string(model.config.values.get("cursor_column")),
                cursor_type=_as_optional_string(model.config.values.get("cursor_type")),
                backfill=BackfillResult(action=BackfillAction.WARN_ONLY),
                custom_materialization_name=(
                    _as_optional_string(model.config.values.get("materialized"))
                    if materialization_type == MaterializationType.CUSTOM
                    else None
                ),
            )
        )
    upstream_deps = build_upstream_deps(project)
    return PlanOutput(
        execution_order=tuple(entry.key for entry in model_entries),
        model_entries=tuple(model_entries),
        selected_keys=frozenset(entry.key for entry in model_entries),
        upstream_deps=upstream_deps,
        downstream_deps=build_downstream_deps(upstream_deps),
    )


def _display_action(materialization_type: MaterializationType) -> PlanAction:
    if materialization_type == MaterializationType.VIEW:
        return PlanAction.CREATE_VIEW
    if materialization_type == MaterializationType.INCREMENTAL:
        return PlanAction.INCREMENTAL_APPEND
    if materialization_type == MaterializationType.CUSTOM:
        return PlanAction.CUSTOM
    return PlanAction.CREATE_TABLE


def _as_optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


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


def _resolve_connection_config(
    *, raw_config: dict[str, object], project_dir: Path, adapter_name: str
) -> dict[str, object]:
    config: dict[str, object] = dict(raw_config)
    database: object | None = config.get("database")
    if (
        adapter_name == BuiltinAdapter.DUCKDB
        and isinstance(database, str)
        and not Path(database).is_absolute()
        and database != ":memory:"
    ):
        config["database"] = str(project_dir / database)
    return config
