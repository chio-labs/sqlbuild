"""Virtual build public entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.spec.models.project import SnapshotsConfig
from sqlbuild.virtual.executor.helpers.build import run_virtual_build as _run_virtual_build
from sqlbuild.virtual.executor.models import VirtualBuildExecutionHooks, VirtualBuildPipelineResult


def run_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    defer_sources_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    virtual_environment_name: str | None = None,
    include_stale_upstreams: bool = False,
    changes_only: bool = False,
    auto_load_sources: bool = False,
    reload_sources: bool = False,
    include_python: bool = True,
    seed_only: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    fail_fast: bool = False,
    allow_snapshot_schema_change: bool = False,
    concurrency: int | None = None,
    cli_vars: dict[str, object] | None = None,
    run_tests: bool = True,
    run_audits: bool = True,
    snapshots: SnapshotsConfig | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    on_plan_ready: Callable[
        [CompiledProject, PlanOutput, tuple[PythonPlanEntry, ...]], VirtualBuildExecutionHooks
    ]
    | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    providers: ProviderContainer | None = None,
) -> VirtualBuildPipelineResult:
    """Execute a virtual-mode build."""

    return _run_virtual_build(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        selected_target=selected_target,
        no_sql_validation=no_sql_validation,
        defer_sources_to=defer_sources_to,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        virtual_environment_name=virtual_environment_name,
        include_stale_upstreams=include_stale_upstreams,
        changes_only=changes_only,
        auto_load_sources=auto_load_sources,
        reload_sources=reload_sources,
        include_python=include_python,
        seed_only=seed_only,
        select=select,
        exclude=exclude,
        fail_fast=fail_fast,
        allow_snapshot_schema_change=allow_snapshot_schema_change,
        concurrency=concurrency,
        cli_vars=cli_vars,
        run_tests=run_tests,
        run_audits=run_audits,
        snapshots=snapshots,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        on_plan_ready=on_plan_ready,
        on_connection_start=on_connection_start,
        on_connection_complete=on_connection_complete,
        on_connection_error=on_connection_error,
        on_progress=on_progress,
        external_sql_reference_resolver=external_sql_reference_resolver,
        providers=providers,
    )
