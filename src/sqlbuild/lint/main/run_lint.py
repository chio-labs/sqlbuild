"""Run the lint pass over a SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import SqlExpansionContext
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.lint._helpers.expansion import build_lint_expansion_context, prepare_lint_body
from sqlbuild.lint._helpers.headers import scan_headers, sql_body_ranges
from sqlbuild.lint._helpers.native import lint_native_headers
from sqlbuild.lint._helpers.native_sql import run_native_sql_lint
from sqlbuild.lint._helpers.project_files import collect_project_files, sort_violations
from sqlbuild.lint._helpers.suppressions import apply_suppressions
from sqlbuild.lint.models import HeaderSpan, LintBody, LintConfig, LintRunResult, LintViolation


def run_lint(
    *,
    project_dir: Path,
    config: LintConfig,
    value_renderer: TypedSqlValueRenderer | None = None,
    selected_paths: frozenset[Path] | None = None,
) -> LintRunResult:
    """Lint all DSL files in the project without modifying anything."""

    files: dict[Path, str] = collect_project_files(
        project_dir=project_dir, selected_paths=selected_paths
    )
    violations: list[LintViolation] = []
    bodies: list[LintBody] = []
    context: SqlExpansionContext | None = _expansion_context(
        project_dir=project_dir,
        native_enabled=config.native_enabled,
        value_renderer=value_renderer,
    )
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
        if context is not None:
            bodies.extend(
                _prepared_bodies(
                    file_path=file_path,
                    contents=contents,
                    headers=headers,
                    context=context,
                )
            )

    if bodies and config.native_enabled:
        native_violations: dict[Path, tuple[LintViolation, ...]] = run_native_sql_lint(
            bodies=tuple(bodies),
            contents_by_path=files,
            config=config,
        )
        for entries in native_violations.values():
            violations.extend(entries)

    return LintRunResult(
        files_checked=len(files),
        violations=sort_violations(
            apply_suppressions(violations=violations, contents_by_path=files)
        ),
        formatted_files=(),
    )


def _expansion_context(
    *,
    project_dir: Path,
    native_enabled: bool,
    value_renderer: TypedSqlValueRenderer | None,
) -> SqlExpansionContext | None:
    if not native_enabled:
        return None
    return build_lint_expansion_context(
        project_dir=project_dir,
        value_renderer=value_renderer,
    )


def _prepared_bodies(
    *,
    file_path: Path,
    contents: str,
    headers: tuple[HeaderSpan, ...],
    context: SqlExpansionContext,
) -> tuple[LintBody, ...]:
    bodies: list[LintBody] = []
    body_start: int
    body_end: int
    for body_start, body_end in sql_body_ranges(contents=contents, headers=headers):
        bodies.append(
            prepare_lint_body(
                file_path=file_path,
                contents=contents,
                body_start=body_start,
                body_end=body_end,
                context=context,
            )
        )
    return tuple(bodies)
