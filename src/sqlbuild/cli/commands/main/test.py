"""CLI test command entry point."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_connection_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.pipeline.main.run import run_test_pipeline
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.shared.helpers.colors import bold, colorize_status, green_bold, supports_color


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
    connection_config: dict[str, object] = resolve_connection_config(
        raw_config=discovered_inputs.project_config.connection,
        project_dir=effective_project_dir,
    )
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        select=select,
        exclude=exclude,
        connection_config=connection_config,
    )

    use_color: bool = not no_color and supports_color()
    test_count: int = len(pipeline_result.plan_output.test_entries)
    model_count: int = len(
        {step.model_name for e in pipeline_result.plan_output.test_entries for step in e.chain}
    )
    header: str = f"Test ({test_count} selected, {model_count} models)"
    styled_header: str = green_bold(header) if use_color else header
    sys.stdout.write(f"\n{styled_header}\n")
    sys.stdout.flush()

    on_complete: Callable[[SqlTestExecutionResult], None] = _build_on_complete(use_color=use_color)
    results: tuple[SqlTestExecutionResult, ...] = run_test_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=connection_config,
        adapter=adapter,
        on_test_complete=on_complete,
    )

    pass_count: int = sum(1 for r in results if r.outcome == SqlTestOutcome.PASS)
    fail_count: int = len(results) - pass_count
    sys.stdout.write(f"\nPASS={pass_count}  FAIL={fail_count}  TOTAL={len(results)}\n")
    sys.stdout.flush()

    return 0 if fail_count == 0 else 1


def _build_on_complete(*, use_color: bool) -> Callable[[SqlTestExecutionResult], None]:
    current_group: list[str] = [""]

    def _on_complete(result: SqlTestExecutionResult) -> None:
        model_name: str = ""
        if result.step_results:
            model_name = result.step_results[0].model_name
        group_name: str = model_name or "(unknown)"
        if group_name != current_group[0]:
            current_group[0] = group_name
            group_header: str = bold(group_name) if use_color else group_name
            sys.stdout.write(f"\n{group_header}\n")

        status_text: str = "PASS" if result.outcome == SqlTestOutcome.PASS else "FAIL"
        status: str = colorize_status(status_text, use_color=use_color)
        sys.stdout.write(f"    {'test':<10}{result.test_name:<40} {status}\n")
        if result.error_message is not None:
            sys.stdout.write(f"{'':>14}{result.error_message}\n")
        sys.stdout.flush()

    return _on_complete
