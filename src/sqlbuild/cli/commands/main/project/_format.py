"""Run the format command."""

from __future__ import annotations

import difflib
from dataclasses import replace
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.lint.runs import (
    prepare_lint_run,
    render_lint_result,
    render_lint_result_json,
)
from sqlbuild.cli.commands._helpers.lint.selection import resolve_lint_inputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.lint.main.has_fixture_typed_null_candidates import (
    has_fixture_typed_null_candidates,
)
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
    config: LintConfig = prepared[0]
    value_renderer: BaseAdapter | None = None
    selected_paths: frozenset[Path] | None = None
    graph: ProjectGraph | None = None
    has_fixture_candidates: bool = has_fixture_typed_null_candidates(project_dir=base_dir)
    if select or exclude or has_fixture_candidates:
        try:
            value_renderer, selected_paths, discovered_inputs = resolve_lint_inputs(
                project_dir=base_dir,
                select=select,
                exclude=exclude,
            )
        except Exception:
            if select or exclude:
                raise
        else:
            config = replace(
                config,
                dialect=value_renderer.sql_analysis_dialect_name or "generic",
            )
            if has_fixture_candidates and selected_paths is None:
                try:
                    graph = build_project_graph(
                        discovered_inputs=discovered_inputs,
                        adapter=value_renderer,
                    )
                except Exception:
                    graph = None
    result: LintRunResult = run_format(
        project_dir=base_dir,
        config=config,
        value_renderer=value_renderer,
        selected_paths=selected_paths,
        compiled_project=(
            graph.project if graph is not None and graph.project.settings.sql_analysis else None
        ),
        adapter=value_renderer,
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
