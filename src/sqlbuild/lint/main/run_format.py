"""Run the format pass over a SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.lint._helpers.headers import scan_headers, sql_body_ranges
from sqlbuild.lint._helpers.native import format_native_headers, lint_native_headers
from sqlbuild.lint._helpers.project_files import collect_project_files, sort_violations
from sqlbuild.lint._helpers.sqruff_engine import run_sqruff_fix, run_sqruff_lint
from sqlbuild.lint.models import HeaderSpan, LintConfig, LintRunResult, LintViolation


def run_format(*, project_dir: Path, config: LintConfig) -> LintRunResult:
    """Format all DSL files in place and report the violations that remain."""

    files: dict[Path, str] = collect_project_files(project_dir=project_dir)
    updated_contents: dict[Path, str] = _apply_fixes(
        files=files, config=config, project_dir=project_dir
    )
    formatted: list[Path] = []
    file_path: Path
    new_contents: str
    for file_path, new_contents in updated_contents.items():
        file_path.write_text(new_contents, encoding="utf-8")
        formatted.append(file_path)
    violations: list[LintViolation] = _lint_final_contents(
        files=files, updated_contents=updated_contents, config=config, project_dir=project_dir
    )
    return LintRunResult(
        files_checked=len(files),
        violations=sort_violations(violations),
        formatted_files=tuple(sorted(formatted)),
    )


def _apply_fixes(
    *, files: dict[Path, str], config: LintConfig, project_dir: Path
) -> dict[Path, str]:
    """Return contents after native header fixes and sqruff body fixes."""

    updated: dict[Path, str] = {}
    file_path: Path
    contents: str
    for file_path, contents in sorted(files.items()):
        native_result: tuple[str, tuple[LintViolation, ...]] = format_native_headers(
            contents=contents,
            file_path=file_path,
            config=config,
        )
        if native_result[0] != contents:
            updated[file_path] = native_result[0]
    if not config.sqruff_enabled:
        return updated

    sqruff_bodies: dict[Path, tuple[str, tuple[tuple[int, int], ...]]] = {}
    for file_path, contents in sorted(files.items()):
        current: str = updated.get(file_path, contents)
        headers: tuple[HeaderSpan, ...] = scan_headers(contents=current)
        sqruff_bodies[file_path] = (current, sql_body_ranges(contents=current, headers=headers))
    fixed: dict[Path, str] = run_sqruff_fix(
        bodies=sqruff_bodies, config=config, project_dir=project_dir
    )
    fixed_path: Path
    fixed_contents: str
    for fixed_path, fixed_contents in fixed.items():
        if fixed_contents != sqruff_bodies[fixed_path][0]:
            updated[fixed_path] = fixed_contents
    return updated


def _lint_final_contents(
    *,
    files: dict[Path, str],
    updated_contents: dict[Path, str],
    config: LintConfig,
    project_dir: Path,
) -> list[LintViolation]:
    """Lint final contents so reported violations match a follow-up lint run."""

    violations: list[LintViolation] = []
    file_path: Path
    contents: str
    for file_path, contents in sorted(files.items()):
        final_contents: str = updated_contents.get(file_path, contents)
        headers: tuple[HeaderSpan, ...] = scan_headers(contents=final_contents)
        violations.extend(
            lint_native_headers(
                contents=final_contents,
                file_path=file_path,
                headers=headers,
                config=config,
            )
        )
        if not config.sqruff_enabled:
            continue
        sqruff_violations: dict[Path, tuple[LintViolation, ...]] = run_sqruff_lint(
            bodies={
                file_path: (
                    final_contents,
                    sql_body_ranges(contents=final_contents, headers=headers),
                )
            },
            config=config,
            project_dir=project_dir,
        )
        for entries in sqruff_violations.values():
            violations.extend(entries)
    return violations
