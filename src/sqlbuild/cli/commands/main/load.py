"""CLI load command entry point."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.execution_json import (
    format_load_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.main.shared.helpers.progress import format_build_header
from sqlbuild.compiler.compile.main.effective_runtime import build_effective_runtime_config
from sqlbuild.compiler.compile.main.effective_settings import build_effective_settings_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSourceFile
from sqlbuild.executor.load.main.run import run_load_pipeline
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.shared.helpers.colors import (
    blue_bold,
    colorize_status,
    dim,
    green_bold,
    supports_color,
)
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.spec.models.source import SourceEntry


def run_load(
    project_dir: Path | None,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    reload: bool = False,
    concurrency: int | None = None,
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the load command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    selected_sources: tuple[SourceEntry, ...] = _select_managed_sources(
        discovered_inputs=discovered_inputs,
        select=select,
        exclude=exclude,
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    ready_header: str = f"Load ready ({len(selected_sources)} selected)"
    styled_ready_header: str = green_bold(ready_header) if use_color else ready_header
    progress_stream.write(f"\n{styled_ready_header}\n\n")
    progress_stream.flush()
    if not selected_sources:
        message: str = "  No managed sources selected."
        progress_stream.write((dim(message) if use_color else message) + "\n")
        progress_stream.write("\nCompleted successfully.\n")
        progress_stream.write("PASS=0  WARN=0  FAIL=0  SKIP=0  TOTAL=0  (0.00s)\n")
        progress_stream.flush()
        write_execution_json_output(
            payload=format_load_execution_json(results=()),
            json_output=json_output,
            json_output_path=json_output_path,
        )
        return 0

    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name,
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
    sources_header: str = f"Sources ({len(selected_sources)})"
    styled_sources_header: str = green_bold(sources_header) if use_color else sources_header
    progress_stream.write(f"{styled_sources_header}\n")
    source: SourceEntry
    for source in selected_sources:
        progress_stream.write(f"  {source.name}\n")
    progress_stream.write("\n")
    progress_stream.flush()
    start: float = time.monotonic()
    on_complete: Callable[[LoadExecutionResult], None] = _build_on_complete(
        stream=progress_stream,
        use_color=use_color,
        source_order={source.name: index for index, source in enumerate(selected_sources, start=1)},
        total_count=len(selected_sources),
    )
    effective_concurrency: int = max(
        1,
        concurrency
        if concurrency is not None
        else build_effective_settings_config(discovered_inputs=discovered_inputs).concurrency,
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    execution_header: str = format_build_header(
        command="sqb load", target=None, concurrency=effective_concurrency
    )
    execution_label: str = blue_bold("Execution") if use_color else "Execution"
    header_detail: str = dim(execution_header) if use_color else execution_header
    progress_stream.write(f"{execution_label}  {header_detail}\n\n")
    progress_stream.flush()
    results: tuple[LoadExecutionResult, ...] = run_load_pipeline(
        sources=selected_sources,
        loader_functions=discovered_inputs.loader_functions,
        connection_config=connection_config,
        adapter=adapter,
        run_id=run_id,
        environment=environment_name,
        vars=effective_vars,
        is_reload=reload,
        max_concurrency=effective_concurrency,
        on_load_complete=on_complete,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
    )
    elapsed: float = time.monotonic() - start
    success_count: int = sum(1 for result in results if result.status.value == "success")
    fail_count: int = sum(1 for result in results if result.status.value == "failed")
    completion_message: str = (
        "Completed successfully." if fail_count == 0 else "Completed with errors."
    )
    progress_stream.write(f"\n{completion_message}\n")
    progress_stream.write(
        f"PASS={success_count}  WARN=0  FAIL={fail_count}  SKIP=0  "
        f"TOTAL={len(results)}  ({elapsed:.2f}s)\n"
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
        sources.extend(source_file.source_entries)
    source_names: frozenset[str] = frozenset(source.name for source in sources)
    managed_names: frozenset[str] = frozenset(
        source.name for source in sources if source.loader is not None
    )
    selector: str
    for selector in (*select, *exclude):
        if selector not in source_names:
            raise CliUserError(
                f"sqb load selector '{selector}' does not match any source",
                code="C901",
                help="Use exact source names declared in sources/*.yml.",
            )
        if selector not in managed_names:
            raise CliUserError(
                f"sqb load selector '{selector}' matches a source with no loader",
                code="C902",
                help="Add a loader to the source or remove it from the load selection.",
            )
    selected_names: frozenset[str] = frozenset(select)
    excluded_names: frozenset[str] = frozenset(exclude)
    return tuple(
        source
        for source in sources
        if source.loader is not None
        if (not selected_names or source.name in selected_names)
        and source.name not in excluded_names
    )


def _build_on_complete(
    *,
    stream: TextIO,
    use_color: bool,
    source_order: dict[str, int],
    total_count: int,
) -> Callable[[LoadExecutionResult], None]:
    def _on_complete(result: LoadExecutionResult) -> None:
        status_text: str = "OK" if result.status.value == "success" else "FAIL"
        status: str = colorize_status(status_text, use_color=use_color)
        duration: str = ""
        if result.duration_ms is not None:
            duration = f"{result.duration_ms / 1000.0:.2f}s"
        rows_loaded: str = f"rows={result.rows_loaded:,}"
        ordinal: int = source_order[result.source_name]
        stream.write(
            f"  {ordinal}/{total_count}  source    "
            f"{result.source_name:<30} {status:<6} {duration}  {rows_loaded}\n"
        )
        if result.error_message is not None:
            stream.write(f"    {result.error_message}\n")
        stream.flush()

    return _on_complete
