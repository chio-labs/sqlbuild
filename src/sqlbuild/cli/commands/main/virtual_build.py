"""CLI orchestration for virtual-mode build."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.compile.target_writer import write_compile_target
from sqlbuild.cli.commands.main.helpers.plan.formatter import format_plan
from sqlbuild.cli.commands.main.shared.helpers.execution_json import (
    format_build_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.main.shared.helpers.parsers import (
    parse_cursor_integer,
    parse_cursor_timestamp,
)
from sqlbuild.cli.commands.main.shared.helpers.progress import (
    BuildProgressCallbacks,
    format_build_footer,
    format_build_header,
)
from sqlbuild.cli.commands.main.shared.helpers.runtime_target_writer import write_runtime_target
from sqlbuild.cli.commands.main.shared.helpers.snapshot_full_refresh import (
    enforce_snapshot_full_refresh_policy,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.shared.helpers.colors import blue_bold, dim
from sqlbuild.shared.helpers.display import DisplayOptions
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.main.build import run_virtual_build as run_virtual_build_pipeline
from sqlbuild.virtual.executor.models import VirtualBuildExecutionHooks, VirtualBuildPipelineResult


def run_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    adapter_name: str,
    connection_config: dict[str, object],
    no_sql_validation: bool = False,
    defer_sources_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    virtual_environment_name: str | None = None,
    auto_load_sources: bool = False,
    reload_sources: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    fail_fast: bool = False,
    allow_snapshot_full_refresh: bool = False,
    allow_snapshot_schema_change: bool = False,
    concurrency: int | None = None,
    verbose: bool = False,
    debug: bool = False,
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
    use_color: bool = False,
    progress_stream: TextIO | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> int:
    """Execute a virtual build and render CLI output."""

    del adapter_name
    stream: TextIO = progress_stream or (sys.stderr if debug or json_output else sys.stdout)
    stream.write("\n")
    stream.flush()
    callbacks_by_ref: list[BuildProgressCallbacks] = []

    def on_plan_ready(
        project: object,
        plan_output: PlanOutput,
    ) -> VirtualBuildExecutionHooks:
        del project
        plan_text: str = format_plan(
            plan_output,
            full_refresh=full_refresh,
            use_color=use_color,
            display_options=DisplayOptions(max_entries_per_section=None if verbose else 50),
        )
        stream.write("\n" + plan_text + "\n\n")
        stream.flush()
        enforce_snapshot_full_refresh_policy(
            plan=plan_output,
            snapshots_config=discovered_inputs.project_config.snapshots,
            allow_snapshot_full_refresh=allow_snapshot_full_refresh,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
        )
        write_compile_target(
            target_dir=project_dir / "target",
            adapter=adapter,
            plan_output=plan_output,
            manifest={},
        )
        callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
            plan=plan_output,
            use_color=use_color,
            verbose=verbose,
            debug=debug or json_output,
        )
        callbacks_by_ref.append(callbacks)
        _write_execution_header(
            stream=stream,
            concurrency=concurrency
            if concurrency is not None
            else discovered_inputs.project_config.settings.concurrency,
            use_color=use_color,
        )
        return VirtualBuildExecutionHooks(
            on_node_start=callbacks.on_node_start,
            on_node_complete=callbacks.on_node_complete,
            on_sub_progress=callbacks.on_sub_progress,
        )

    result: VirtualBuildPipelineResult = run_virtual_build_pipeline(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        no_sql_validation=no_sql_validation,
        defer_sources_to=defer_sources_to,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        virtual_environment_name=virtual_environment_name,
        auto_load_sources=auto_load_sources,
        reload_sources=reload_sources,
        select=select,
        exclude=exclude,
        fail_fast=fail_fast,
        allow_snapshot_schema_change=allow_snapshot_schema_change,
        concurrency=concurrency,
        cli_vars=cli_vars,
        snapshots=discovered_inputs.project_config.snapshots,
        start_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).start_ts),
        end_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).end_ts),
        start_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).start_int),
        end_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).end_int),
        on_plan_ready=on_plan_ready,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    plan_output: PlanOutput = result.plan_output
    footer: str = format_build_footer(
        result=result.execution_result,
        elapsed=callbacks_by_ref[0].elapsed if callbacks_by_ref else 0,
        use_color=use_color,
    )
    write_runtime_target(
        target_dir=project_dir / "target",
        plan_output=plan_output,
        result=result.execution_result,
    )
    stream.write("\n" + footer + "\n")
    stream.flush()
    write_execution_json_output(
        payload=format_build_execution_json(result=result.execution_result, plan=plan_output),
        json_output=json_output,
        json_output_path=json_output_path,
    )
    return 0 if result.execution_result.status == BuildStatus.SUCCESS else 1


def _write_execution_header(*, stream: TextIO, concurrency: int, use_color: bool) -> None:
    header: str = format_build_header(command="sqb build", target=None, concurrency=concurrency)
    execution_label: str = blue_bold("Execution") if use_color else "Execution"
    header_detail: str = dim(header) if use_color else header
    stream.write(f"{execution_label}  {header_detail}\n\n")
    stream.flush()
