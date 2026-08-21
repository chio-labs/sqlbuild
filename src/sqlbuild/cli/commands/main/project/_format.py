"""Run the format command."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.lint.runs import render_lint_result, resolve_lint_config
from sqlbuild.lint.main.run_format import run_format
from sqlbuild.lint.models import LintRunResult


def run_format_command(*, project_dir: Path | None, no_sqruff: bool = False) -> int:
    """Apply autofixes in place; non-zero when faults remain after formatting."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    result: LintRunResult = run_format(
        project_dir=base_dir,
        config=resolve_lint_config(project_dir=base_dir, no_sqruff=no_sqruff),
    )
    _ = render_lint_result(result=result, show_formatted=True)
    return 1 if result.faults else 0
