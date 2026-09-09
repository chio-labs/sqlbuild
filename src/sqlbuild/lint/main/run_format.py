"""Run the format pass over a SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.lint._helpers.headers import scan_headers
from sqlbuild.lint._helpers.native import format_native_headers, lint_native_headers
from sqlbuild.lint._helpers.native_format import (
    format_native_sql_bodies,
    newline_style,
    with_newline_style,
)
from sqlbuild.lint._helpers.project_files import collect_project_files, sort_violations
from sqlbuild.lint._helpers.suppressions import apply_suppressions
from sqlbuild.lint.models import (
    FormatChange,
    HeaderSpan,
    LintConfig,
    LintRunResult,
    LintViolation,
)


def run_format(
    *,
    project_dir: Path,
    config: LintConfig,
    value_renderer: TypedSqlValueRenderer | None = None,
    selected_paths: frozenset[Path] | None = None,
    write: bool = True,
) -> LintRunResult:
    """Format all DSL files in place and report the violations that remain."""

    files: dict[Path, str] = collect_project_files(
        project_dir=project_dir, selected_paths=selected_paths
    )
    newline_by_path: dict[Path, str] = {
        file_path: newline_style(contents=contents) for file_path, contents in files.items()
    }
    updated_contents: dict[Path, str] = _apply_fixes(
        files=files, config=config, project_dir=project_dir
    )
    formatted: list[Path] = []
    changes: list[FormatChange] = []
    file_path: Path
    new_contents: str
    for file_path, new_contents in updated_contents.items():
        rendered_contents: str = with_newline_style(
            contents=new_contents, newline=newline_by_path[file_path]
        )
        original_contents: str = with_newline_style(
            contents=files[file_path], newline=newline_by_path[file_path]
        )
        if rendered_contents == original_contents:
            continue
        changes.append(
            FormatChange(
                file_path=file_path,
                before=original_contents,
                after=rendered_contents,
            )
        )
        if write:
            with file_path.open("w", encoding="utf-8", newline="") as handle:
                _ = handle.write(rendered_contents)
        formatted.append(file_path)
    violations: list[LintViolation] = _lint_final_contents(
        files=files,
        updated_contents=updated_contents,
        config=config,
        project_dir=project_dir,
        value_renderer=value_renderer,
    )
    final_contents: dict[Path, str] = {
        path: updated_contents.get(path, contents) for path, contents in files.items()
    }
    return LintRunResult(
        files_checked=len(files),
        violations=sort_violations(
            apply_suppressions(
                violations=violations,
                contents_by_path=final_contents,
            )
        ),
        formatted_files=tuple(sorted(formatted)),
        format_changes=tuple(sorted(changes, key=lambda change: change.file_path)),
        source_texts=final_contents,
    )


def _apply_fixes(
    *, files: dict[Path, str], config: LintConfig, project_dir: Path
) -> dict[Path, str]:
    """Return contents after native header and supported SQL body fixes."""

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
    if not config.native_enabled:
        return updated
    current_files: dict[Path, str] = {
        file_path: updated.get(file_path, contents) for file_path, contents in files.items()
    }
    updated.update(
        format_native_sql_bodies(
            files=current_files,
            config=config,
            project_dir=project_dir,
        )
    )
    return updated


def _lint_final_contents(
    *,
    files: dict[Path, str],
    updated_contents: dict[Path, str],
    config: LintConfig,
    project_dir: Path,
    value_renderer: TypedSqlValueRenderer | None,
) -> list[LintViolation]:
    """Return formatter-owned header diagnostics without enforcing configured Rules."""

    del project_dir, value_renderer
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
    return violations
