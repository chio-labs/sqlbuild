"""Run the native lint fixer command."""

from __future__ import annotations

import difflib
from dataclasses import replace
from pathlib import Path

from sqlbuild.cli.commands._helpers.lint.runs import (
    prepare_lint_run,
    render_fix_result,
    render_fix_result_json,
)
from sqlbuild.cli.commands._helpers.lint.selection import resolve_lint_inputs
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.lint.main.run_fix import run_fix
from sqlbuild.lint.models import FixRunResult, FormatChange, LintConfig
from sqlbuild.presentation.main.supports_color import supports_color


def run_fix_command(
    *,
    project_dir: Path | None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    check: bool = False,
    diff: bool = False,
    json_output: bool = False,
    no_color: bool = False,
) -> int:
    """Apply eligible native lint repairs or preview them without writing."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    prepared: tuple[LintConfig, str | None] = prepare_lint_run(project_dir=base_dir)
    config: LintConfig = prepared[0]
    warning: str | None = prepared[1]
    if warning is not None:
        print(f"WARN  {warning}")
    value_renderer: TypedSqlValueRenderer | None = None
    selected_paths: frozenset[Path] | None = None
    if select or exclude:
        value_renderer, selected_paths, _discovered_inputs = resolve_lint_inputs(
            project_dir=base_dir,
            select=select,
            exclude=exclude,
        )
        config = replace(
            config,
            dialect=value_renderer.sql_analysis_dialect_name or "generic",
        )
    preview: bool = check or diff
    result: FixRunResult = run_fix(
        project_dir=base_dir,
        config=config,
        value_renderer=value_renderer,
        selected_paths=selected_paths,
        write=not preview,
    )
    if diff:
        _ = _render_fix_diff(result=result)
    if json_output:
        _ = render_fix_result_json(result=result, preview=preview)
    else:
        _ = render_fix_result(
            result=result,
            root=base_dir,
            use_color=not no_color and supports_color(),
            preview=preview,
        )
    return 1 if result.violations or (preview and result.changed_files) else 0


def _render_fix_diff(*, result: FixRunResult) -> None:
    for change in result.changes:
        _ = _print_change(change=change)


def _print_change(*, change: FormatChange) -> None:
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
