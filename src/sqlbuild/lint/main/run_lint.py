"""Run the lint pass over a SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.lint._helpers.headers import scan_headers, sql_body_ranges
from sqlbuild.lint._helpers.native import lint_native_headers
from sqlbuild.lint._helpers.project_files import collect_project_files, sort_violations
from sqlbuild.lint._helpers.sqruff_engine import run_sqruff_lint
from sqlbuild.lint.models import HeaderSpan, LintConfig, LintRunResult, LintViolation


def run_lint(*, project_dir: Path, config: LintConfig) -> LintRunResult:
    """Lint all DSL files in the project without modifying anything."""

    files: dict[Path, str] = collect_project_files(project_dir=project_dir)
    violations: list[LintViolation] = []
    sqruff_bodies: dict[Path, tuple[str, tuple[tuple[int, int], ...]]] = {}
    file_path: Path
    contents: str
    for file_path, contents in sorted(files.items()):
        headers: tuple[HeaderSpan, ...] = scan_headers(contents=contents)
        violations.extend(
            lint_native_headers(
                contents=contents,
                file_path=file_path,
                headers=headers,
                config=config,
            )
        )
        if config.sqruff_enabled:
            sqruff_bodies[file_path] = (
                contents,
                sql_body_ranges(contents=contents, headers=headers),
            )

    if config.sqruff_enabled and sqruff_bodies:
        sqruff_violations: dict[Path, tuple[LintViolation, ...]] = run_sqruff_lint(
            bodies=sqruff_bodies,
            config=config,
            project_dir=project_dir,
        )
        for entries in sqruff_violations.values():
            violations.extend(entries)

    return LintRunResult(
        files_checked=len(files),
        violations=sort_violations(violations),
        formatted_files=(),
    )
