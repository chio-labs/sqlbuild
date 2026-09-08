"""Project custom SQL lint evaluation entrypoint."""

from pathlib import Path

from sqlbuild.lint._helpers.custom_rules import run_custom_lint_rules
from sqlbuild.lint.models import LintBody, LintConfig, LintViolation


def evaluate_custom_lint_rules(
    *,
    bodies: tuple[LintBody, ...],
    contents_by_path: dict[Path, str],
    config: LintConfig,
    project_dir: Path,
) -> tuple[LintViolation, ...]:
    """Evaluate selected custom rules over prepared statement bodies."""

    return run_custom_lint_rules(
        bodies=bodies,
        contents_by_path=contents_by_path,
        config=config,
        project_dir=project_dir,
    )
