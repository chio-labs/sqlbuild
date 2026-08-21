"""Run the lint command."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.lint.runs import prepare_lint_run, render_lint_result
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import LintConfig, LintRunResult


def run_lint_command(*, project_dir: Path | None, no_sqruff: bool = False) -> int:
    """Report lint violations without modifying authored files; non-zero on violations."""

    base_dir: Path = project_dir if project_dir is not None else Path.cwd()
    prepared: tuple[LintConfig, str | None] = prepare_lint_run(
        project_dir=base_dir, no_sqruff=no_sqruff
    )
    if prepared[1] is not None:
        print(f"WARN  {prepared[1]}")
    result: LintRunResult = run_lint(project_dir=base_dir, config=prepared[0])
    _ = render_lint_result(result=result, show_formatted=False)
    return 1 if result.violations else 0
