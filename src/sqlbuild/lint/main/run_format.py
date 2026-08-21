"""Run the format pass over a SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import SqlExpansionContext
from sqlbuild.lint._helpers.expansion import build_lint_expansion_context, prepare_lint_body
from sqlbuild.lint._helpers.headers import scan_headers, sql_body_ranges
from sqlbuild.lint._helpers.native import format_native_headers, lint_native_headers
from sqlbuild.lint._helpers.newlines import newline_style, with_newline_style
from sqlbuild.lint._helpers.project_files import collect_project_files, sort_violations
from sqlbuild.lint._helpers.sqruff_engine import run_sqruff_fix, run_sqruff_lint
from sqlbuild.lint.models import (
    HeaderSpan,
    LintBody,
    LintConfig,
    LintRunResult,
    LintViolation,
)


def run_format(*, project_dir: Path, config: LintConfig) -> LintRunResult:
    """Format all DSL files in place and report the violations that remain."""

    files: dict[Path, str] = collect_project_files(project_dir=project_dir)
    newline_by_path: dict[Path, str] = {
        file_path: newline_style(contents=contents) for file_path, contents in files.items()
    }
    updated_contents: dict[Path, str] = _apply_fixes(
        files=files, config=config, project_dir=project_dir
    )
    formatted: list[Path] = []
    file_path: Path
    new_contents: str
    for file_path, new_contents in updated_contents.items():
        with file_path.open("w", encoding="utf-8", newline="") as handle:
            _ = handle.write(
                with_newline_style(contents=new_contents, newline=newline_by_path[file_path])
            )
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
    final_by_path: dict[Path, str] = {}
    bodies: list[LintBody] = []
    context: SqlExpansionContext | None = None
    if config.sqruff_enabled:
        context = build_lint_expansion_context(project_dir=project_dir)
    file_path: Path
    contents: str
    for file_path, contents in sorted(files.items()):
        final_contents: str = updated_contents.get(file_path, contents)
        final_by_path[file_path] = final_contents
        headers: tuple[HeaderSpan, ...] = scan_headers(contents=final_contents)
        violations.extend(
            lint_native_headers(
                contents=final_contents,
                file_path=file_path,
                headers=headers,
                config=config,
            )
        )
        if context is None:
            continue
        body_start: int
        body_end: int
        for body_start, body_end in sql_body_ranges(contents=final_contents, headers=headers):
            bodies.append(
                prepare_lint_body(
                    file_path=file_path,
                    contents=final_contents,
                    body_start=body_start,
                    body_end=body_end,
                    context=context,
                )
            )
    if not bodies:
        return violations
    sqruff_violations: dict[Path, tuple[LintViolation, ...]] = run_sqruff_lint(
        bodies=tuple(bodies),
        contents_by_path=final_by_path,
        config=config,
        project_dir=project_dir,
    )
    entries: tuple[LintViolation, ...]
    for entries in sqruff_violations.values():
        violations.extend(entries)
    return violations
