"""CLI test command entry point."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.colors import colorize_status, supports_color
from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.pipeline.main import run_test_pipeline
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome


def run_test(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> int:
    """Execute the test command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(discovered_inputs.project_config.adapter)
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        select=select,
        exclude=exclude,
    )

    use_color: bool = not no_color and supports_color()
    sys.stdout.write("sqb test\n\n")
    sys.stdout.flush()

    on_complete: Callable[[SqlTestExecutionResult], None] = _build_on_complete(use_color=use_color)
    results: tuple[SqlTestExecutionResult, ...] = run_test_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=dict(discovered_inputs.project_config.connection),
        adapter=adapter,
        on_test_complete=on_complete,
    )

    pass_count: int = sum(1 for r in results if r.outcome == SqlTestOutcome.PASS)
    fail_count: int = len(results) - pass_count
    sys.stdout.write(f"\nPASS={pass_count}  FAIL={fail_count}  TOTAL={len(results)}\n")
    sys.stdout.flush()

    return 0 if fail_count == 0 else 1


def _build_on_complete(*, use_color: bool) -> Callable[[SqlTestExecutionResult], None]:
    def _on_complete(result: SqlTestExecutionResult) -> None:
        status_text: str = "PASS" if result.outcome == SqlTestOutcome.PASS else "FAIL"
        status: str = colorize_status(status_text, use_color=use_color)
        sys.stdout.write(f"  {result.test_name:<50} {status}\n")
        if result.error_message is not None:
            sys.stdout.write(f"    {result.error_message}\n")
        sys.stdout.flush()

    return _on_complete
