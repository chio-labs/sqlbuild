"""CLI seed command entry point."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_connection_config
from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.build.types import ExecutionStatus
from sqlbuild.executor.pipeline.main import run_seed_pipeline
from sqlbuild.shared.helpers.colors import colorize_status, supports_color


def run_seed(
    project_dir: Path | None,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> int:
    """Execute the seed command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(discovered_inputs.project_config.adapter)
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=discovered_inputs.project_config.connection,
        project_dir=effective_project_dir,
    )
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        select=select,
        exclude=exclude,
        connection_config=connection_config,
    )

    use_color: bool = not no_color and supports_color()
    sys.stdout.write("sqb seed\n\n")
    sys.stdout.flush()

    start: float = time.monotonic()
    on_complete: Callable[[SeedExecutionResult], None] = _build_on_complete(use_color=use_color)
    results: tuple[SeedExecutionResult, ...] = run_seed_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=connection_config,
        adapter=adapter,
        on_seed_complete=on_complete,
    )
    elapsed: float = time.monotonic() - start

    success_count: int = sum(1 for r in results if r.status == ExecutionStatus.SUCCESS)
    fail_count: int = sum(1 for r in results if r.status == ExecutionStatus.FAILED)
    elapsed_str: str = f"{elapsed:.2f}s"
    completion: str = (
        colorize_status("OK", use_color=use_color)
        if fail_count == 0
        else colorize_status("FAIL", use_color=use_color)
    )
    sys.stdout.write(
        f"\n{completion}  {success_count} loaded, {fail_count} failed  ({elapsed_str})\n"
    )
    sys.stdout.flush()

    return 0 if fail_count == 0 else 1


def _build_on_complete(*, use_color: bool) -> Callable[[SeedExecutionResult], None]:
    def _on_complete(result: SeedExecutionResult) -> None:
        status_text: str = "OK" if result.status == ExecutionStatus.SUCCESS else "FAIL"
        status: str = colorize_status(status_text, use_color=use_color)
        duration: str = ""
        if result.duration_ms is not None:
            seconds: float = result.duration_ms / 1000.0
            duration = f"{seconds:.2f}s"
        sys.stdout.write(f"  {result.seed_name:<50} {status:<6} {duration}\n")
        if result.error_message is not None:
            sys.stdout.write(f"    {result.error_message}\n")
        sys.stdout.flush()

    return _on_complete
