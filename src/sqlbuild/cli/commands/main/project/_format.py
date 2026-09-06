"""Run the format command."""

from __future__ import annotations

import difflib
from dataclasses import replace
from pathlib import Path

from sqlbuild.cli.commands._helpers.lint.runs import (
    prepare_lint_run,
    render_lint_result,
    render_lint_result_json,
)
from sqlbuild.cli.commands._helpers.lint.selection import resolve_lint_inputs
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.lint.main.run_format import run_format
from sqlbuild.lint.models import LintConfig, LintRunResult
from sqlbuild.presentation.main.supports_color import supports_color


def run_format_command(
    *,
    project_dir: Path | None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    check: bool = False,
    diff: bool = False,
    json_output: bool = False,
    no_color: bool = False,
) -> int:
    """Apply autofixes in place; non-zero when faults remain after formatting."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    prepared: tuple[LintConfig, str | None] = prepare_lint_run(project_dir=base_dir)
    if prepared[1] is not None:
        print(f"WARN  {prepared[1]}")
    value_renderer: TypedSqlValueRenderer | None = None
    selected_paths: frozenset[Path] | None = None
    config: LintConfig = prepared[0]
    if select or exclude:
        value_renderer, selected_paths = resolve_lint_inputs(
            project_dir=base_dir,
            select=select,
            exclude=exclude,
        )
        config = replace(
            config,
            dialect=value_renderer.sql_analysis_dialect_name or "generic",
        )
    result: LintRunResult = run_format(
        project_dir=base_dir,
        config=config,
        value_renderer=value_renderer,
        selected_paths=selected_paths,
        write=not (check or diff),
    )
    if diff:
        _ = _render_format_diff(result=result)
    if json_output:
        _ = render_lint_result_json(result=result)
    else:
        _ = render_lint_result(
            result=result,
            root=base_dir,
            use_color=not no_color and supports_color(),
            show_formatted=True,
            formatted_heading="Would format files:" if check or diff else "Formatted files:",
        )
    return 1 if result.violations or (check and result.formatted_files) else 0


def _render_format_diff(*, result: LintRunResult) -> None:
    """Print stable unified diffs for files the formatter would change."""

    for change in result.format_changes:
        print(
            "".join(
                difflib.unified_diff(
                    change.before.splitlines(keepends=True),
                    change.after.splitlines(keepends=True),
                    fromfile=str(change.file_path),
                    tofile=str(change.file_path),
                )
            ),
            end="",
        )
