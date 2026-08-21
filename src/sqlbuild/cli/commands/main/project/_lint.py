"""Run the lint command."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.lint.runs import render_lint_result, resolve_lint_config
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import LintRunResult


def run_lint_command(*, project_dir: Path | None, no_sqruff: bool = False) -> int:
    """Report lint violations without modifying files; non-zero on any violation."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    result: LintRunResult = run_lint(
        project_dir=base_dir,
        config=resolve_lint_config(project_dir=base_dir, no_sqruff=no_sqruff),
    )
    _ = render_lint_result(result=result, show_formatted=False)
    return 1 if result.violations else 0
