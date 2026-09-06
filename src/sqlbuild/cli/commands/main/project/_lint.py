"""Run the lint command."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.cli.commands._helpers.lint.runs import (
    prepare_lint_run,
    render_lint_result,
    render_lint_result_json,
)
from sqlbuild.cli.commands._helpers.lint.selection import resolve_lint_inputs
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import LintConfig, LintRunResult
from sqlbuild.presentation.main.supports_color import supports_color


def run_lint_command(
    *,
    project_dir: Path | None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    json_output: bool = False,
    no_color: bool = False,
) -> int:
    """Report lint violations without modifying authored files; non-zero on violations."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    prepared: tuple[LintConfig, str | None] = prepare_lint_run(project_dir=base_dir)
    if prepared[1] is not None:
        print(f"WARN  {prepared[1]}")
    value_renderer, selected_paths, discovered_inputs = resolve_lint_inputs(
        project_dir=base_dir,
        select=select,
        exclude=exclude,
    )
    config: LintConfig = replace(
        prepared[0],
        dialect=value_renderer.sql_analysis_dialect_name or "generic",
    )
    result: LintRunResult = run_lint(
        project_dir=base_dir,
        config=config,
        value_renderer=value_renderer,
        selected_paths=selected_paths,
        discovered_inputs=discovered_inputs,
    )
    if json_output:
        _ = render_lint_result_json(result=result)
    else:
        _ = render_lint_result(
            result=result,
            root=base_dir,
            use_color=not no_color and supports_color(),
            show_formatted=False,
        )
    return 1 if result.violations else 0
