"""CLI load command entry point."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.load.progress import (
    LoadProgressReporter,
    format_load_footer,
)
from sqlbuild.cli.commands.helpers.load.references import validate_reference_source_targets
from sqlbuild.cli.commands.helpers.load.selection import (
    select_load_entries,
    select_load_reference_entries,
)
from sqlbuild.cli.commands.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.shared.helpers.config.parsers import (
    parse_cursor_integer,
    parse_cursor_timestamp,
)
from sqlbuild.cli.commands.shared.helpers.connection.core import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.shared.helpers.output.execution_json import (
    format_load_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.shared.helpers.progress.connection import ConnectionProgressReporter
from sqlbuild.cli.commands.shared.helpers.progress.core import write_execution_header
from sqlbuild.compiler.compile.main.effective_runtime import build_effective_runtime_config
from sqlbuild.compiler.compile.main.effective_settings import build_effective_settings_config
from sqlbuild.compiler.compile.main.effective_target import build_effective_target_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.executor.load.main.run import run_load_pipeline
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.provider.main.session import build_provider_session
from sqlbuild.shared.helpers.output.cli_style import CliStyle
from sqlbuild.shared.helpers.output.colors import supports_color
from sqlbuild.shared.main.summary_footer import format_summary_footer
from sqlbuild.spec.models.project import TargetConfig, resolve_effective_adapter_name
from sqlbuild.spec.models.source import SourceEntry


def run_load(
    project_dir: Path | None,
    no_color: bool = False,
    selected_target: str | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    reload: bool = False,
    concurrency: int | None = None,
    cursor_overrides: CursorOverrides | None = None,
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the load command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    selected_sources: tuple[SourceEntry, ...] = select_load_entries(
        discovered_inputs=discovered_inputs,
        select=select,
        exclude=exclude,
        target_config=build_effective_target_config(
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
        ),
    )
    target_config: TargetConfig | None = build_effective_target_config(
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
    )
    reference_sources: tuple[SourceEntry, ...] = select_load_reference_entries(
        discovered_inputs=discovered_inputs,
        selected_sources=selected_sources,
        target_config=target_config,
    )
    use_color: bool = not no_color and supports_color()
    style: CliStyle = CliStyle(use_color=use_color)
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    ready_header: str = f"Load ready ({len(selected_sources)} selected)"
    styled_ready_header: str = style.success_strong(ready_header)
    progress_stream.write(f"\n{styled_ready_header}\n\n")
    progress_stream.flush()
    if not selected_sources:
        message: str = "  No managed sources selected."
        progress_stream.write(style.muted(message) + "\n")
        progress_stream.write("\nCompleted successfully.\n")
        progress_stream.write(
            format_summary_footer(
                counts=(
                    ("PASS", 0),
                    ("WARN", 0),
                    ("FAIL", 0),
                    ("SKIP", 0),
                    ("TOTAL", 0),
                ),
                use_color=use_color,
                elapsed="0.00s",
            )
            + "\n"
        )
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
        selected_target=selected_target,
        cli_vars=cli_vars,
    )
    validate_reference_source_targets(
        adapter=adapter,
        connection_config=connection_config,
        selected_sources=selected_sources,
        reference_sources=reference_sources,
    )
    target_name: str | None
    effective_vars: dict[str, object]
    run_id: str
    target_name, effective_vars, run_id = build_effective_runtime_config(
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
        cli_vars=cli_vars,
    )
    effective_cursor_overrides: CursorOverrides = cursor_overrides or CursorOverrides()
    loader_entries: tuple[SourceEntry, ...] = tuple(
        source for source in selected_sources if _is_loader_node(source)
    )
    source_entries: tuple[SourceEntry, ...] = tuple(
        source for source in selected_sources if not _is_loader_node(source)
    )
    if loader_entries:
        loaders_header: str = f"Loaders ({len(loader_entries)})"
        styled_loaders_header: str = style.success_strong(loaders_header)
        progress_stream.write(f"{styled_loaders_header}\n")
        for source in loader_entries:
            progress_stream.write(f"  {source.name}\n")
        progress_stream.write("\n")
    sources_header: str = f"Sources ({len(source_entries)})"
    styled_sources_header: str = style.success_strong(sources_header)
    progress_stream.write(f"{styled_sources_header}\n")
    source: SourceEntry
    for source in source_entries:
        progress_stream.write(f"  {source.name}\n")
    progress_stream.write("\n")
    progress_stream.flush()
    start: float = time.monotonic()
    load_progress: LoadProgressReporter = LoadProgressReporter(
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
    write_execution_header(
        stream=progress_stream,
        command="sqb load",
        target=None,
        concurrency=effective_concurrency,
        use_color=use_color,
    )
    provider_session: Any = build_provider_session(discovered_inputs.providers)
    try:
        results: tuple[LoadExecutionResult, ...] = run_load_pipeline(
            sources=selected_sources,
            reference_sources=reference_sources,
            loader_functions=discovered_inputs.loader_functions,
            connection_config=connection_config,
            adapter=adapter,
            run_id=run_id,
            runtime_dir=effective_project_dir / "target",
            target=target_name,
            vars=effective_vars,
            is_reload=reload,
            start_cursor_ts=parse_cursor_timestamp(effective_cursor_overrides.start_ts),
            end_cursor_ts=parse_cursor_timestamp(effective_cursor_overrides.end_ts),
            start_cursor_int=parse_cursor_integer(effective_cursor_overrides.start_int),
            end_cursor_int=parse_cursor_integer(effective_cursor_overrides.end_int),
            max_concurrency=effective_concurrency,
            on_load_start=load_progress.on_start,
            on_load_progress=load_progress.on_progress,
            on_load_complete=load_progress.on_complete,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=connection_progress.on_connection_complete,
            on_connection_error=connection_progress.on_connection_error,
            use_color=use_color,
            providers=provider_session.providers,
        )
        elapsed: float = time.monotonic() - start
        success_count: int = sum(1 for result in results if result.status.value == "success")
        fail_count: int = sum(1 for result in results if result.status.value == "failed")
        skip_count: int = sum(1 for result in results if result.status.value == "skipped")
        progress_stream.write(
            format_load_footer(
                success_count=success_count,
                fail_count=fail_count,
                skip_count=skip_count,
                total_count=len(results),
                elapsed=elapsed,
                use_color=use_color,
            )
        )
        progress_stream.flush()
        write_execution_json_output(
            payload=format_load_execution_json(results=results),
            json_output=json_output,
            json_output_path=json_output_path,
        )
        return 0 if fail_count == 0 else 1
    finally:
        provider_session.close()


def _is_loader_node(source: SourceEntry) -> bool:
    return source.meta.get("sqlbuild_loader_node") is True
