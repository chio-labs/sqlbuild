"""CLI load command entry point."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.execution_json import (
    format_load_execution_json,
    write_execution_json_output,
)
from sqlbuild.compiler.compile.main.effective_runtime import build_effective_runtime_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSourceFile
from sqlbuild.executor.load.main.run import run_load_pipeline
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.shared.helpers.colors import colorize_status, supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.spec.models.source import SourceEntry


def run_load(
    project_dir: Path | None,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    reload: bool = False,
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the load command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        cli_vars=cli_vars,
    )
    environment_name: str | None
    effective_vars: dict[str, object]
    run_id: str
    environment_name, effective_vars, run_id = build_effective_runtime_config(
        discovered_inputs=discovered_inputs,
        cli_vars=cli_vars,
    )
    selected_sources: tuple[SourceEntry, ...] = _select_managed_sources(
        discovered_inputs=discovered_inputs,
        select=select,
        exclude=exclude,
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    progress_stream.write("sqb load\n\n")
    progress_stream.flush()

    start: float = time.monotonic()
    on_complete: Callable[[LoadExecutionResult], None] = _build_on_complete(
        stream=progress_stream,
        use_color=use_color,
    )
    results: tuple[LoadExecutionResult, ...] = run_load_pipeline(
        sources=selected_sources,
        loader_functions=discovered_inputs.loader_functions,
        connection_config=connection_config,
        adapter=adapter,
        run_id=run_id,
        environment=environment_name,
        vars=effective_vars,
        is_reload=reload,
        on_load_complete=on_complete,
    )
    elapsed: float = time.monotonic() - start
    success_count: int = sum(1 for result in results if result.status.value == "success")
    fail_count: int = sum(1 for result in results if result.status.value == "failed")
    completion: str = (
        colorize_status("OK", use_color=use_color)
        if fail_count == 0
        else colorize_status("FAIL", use_color=use_color)
    )
    progress_stream.write(
        f"\n{completion}  {success_count} loaded, {fail_count} failed  ({elapsed:.2f}s)\n"
    )
    progress_stream.flush()
    write_execution_json_output(
        payload=format_load_execution_json(results=results),
        json_output=json_output,
        json_output_path=json_output_path,
    )
    return 0 if fail_count == 0 else 1


def _select_managed_sources(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> tuple[SourceEntry, ...]:
    sources: list[SourceEntry] = []
    source_file: DiscoveredSourceFile
    for source_file in discovered_inputs.source_files:
        sources.extend(source for source in source_file.source_entries if source.loader is not None)
    selected_names: frozenset[str] = frozenset(select)
    excluded_names: frozenset[str] = frozenset(exclude)
    return tuple(
        source
        for source in sources
        if (not selected_names or source.name in selected_names)
        and source.name not in excluded_names
    )


def _build_on_complete(*, stream: TextIO, use_color: bool) -> Callable[[LoadExecutionResult], None]:
    def _on_complete(result: LoadExecutionResult) -> None:
        status_text: str = "OK" if result.status.value == "success" else "FAIL"
        status: str = colorize_status(status_text, use_color=use_color)
        duration: str = ""
        if result.duration_ms is not None:
            duration = f"{result.duration_ms / 1000.0:.2f}s"
        stream.write(f"  {result.source_name:<50} {status:<6} {duration}\n")
        if result.error_message is not None:
            stream.write(f"    {result.error_message}\n")
        stream.flush()

    return _on_complete
