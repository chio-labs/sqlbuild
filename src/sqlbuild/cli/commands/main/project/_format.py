"""Run the format command."""

from __future__ import annotations

import difflib
import sys
import time
from dataclasses import replace
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.lint.runs import (
    prepare_lint_run,
    render_lint_result,
    render_lint_result_json,
)
from sqlbuild.cli.commands._helpers.lint.selection import resolve_lint_inputs
from sqlbuild.compiler.discovery.constants import SQL_ANALYSIS_SETTING_KEY
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint.main.has_fixture_typed_null_candidates import (
    has_fixture_typed_null_candidates,
)
from sqlbuild.lint.main.run_format import run_format
from sqlbuild.lint.models import LintConfig, LintRunResult
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.supports_color import supports_color


def run_format_command(
    *,
    project_dir: Path | None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    check: bool = False,
    diff: bool = False,
    fixtures_only: bool = False,
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
    discovered_inputs: DiscoveredProjectInputs | None = None
    has_fixture_candidates: bool = False
    if not select and not exclude:
        has_fixture_candidates = has_fixture_typed_null_candidates(project_dir=base_dir)
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
            has_fixture_candidates = bool(discovered_inputs.test_files)
            config = replace(
                config,
                dialect=value_renderer.sql_analysis_dialect_name or "generic",
            )
    fixture_inputs: DiscoveredProjectInputs | None = None
    if discovered_inputs is not None and has_fixture_candidates:
        local_overrides: frozenset[str] = discovered_inputs.local_config.setting_overrides
        sql_analysis_enabled: bool = (
            discovered_inputs.local_config.settings.sql_analysis
            if SQL_ANALYSIS_SETTING_KEY in local_overrides
            else discovered_inputs.project_config.settings.sql_analysis
        )
        if sql_analysis_enabled:
            fixture_inputs = discovered_inputs
    format_started_at: float = time.monotonic()
    format_status: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stderr,
        use_color=not no_color and supports_color(),
    )
    format_status.start("Formatting SQL  START")
    try:
        result: LintRunResult = run_format(
            project_dir=base_dir,
            config=config,
            value_renderer=value_renderer,
            selected_paths=selected_paths,
            discovered_inputs=fixture_inputs,
            fixtures_only=fixtures_only,
            write=not (check or diff),
        )
    except Exception:
        format_status.error("Formatting SQL  ERROR")
        raise
    elapsed_seconds: float = time.monotonic() - format_started_at
    format_status.complete(
        message=(
            f"Formatting SQL  OK  ({elapsed_seconds:.2f}s; "
            f"{result.files_checked} files checked, {len(result.formatted_files)} changed)"
        )
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
    return 1 if result.faults or (check and result.formatted_files) else 0


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
