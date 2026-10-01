"""Run the format pass over a SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.classes.fixture_null_autofix import FixtureNullAutofix
from sqlbuild.lint._helpers.fixes import finalize_fix_reports, persist_changes, plan_rule_fixes
from sqlbuild.lint._helpers.headers import scan_headers
from sqlbuild.lint._helpers.native import (
    format_native_headers,
    lint_native_headers,
    prepare_native_header_cache,
    reject_unparseable_header_rewrites,
    safe_format_files,
)
from sqlbuild.lint._helpers.native_format import format_native_sql_bodies
from sqlbuild.lint._helpers.project_files import collect_project_files, sort_violations
from sqlbuild.lint._helpers.suppressions import apply_suppressions
from sqlbuild.lint.constants import VIOLATION_SEVERITY_WARNING
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
    discovered_inputs: DiscoveredProjectInputs | None = None,
    fixtures_only: bool = False,
    write: bool = True,
    fix: bool = False,
) -> LintRunResult:
    """Format all DSL files in place and report the violations that remain."""

    files: dict[Path, str] = collect_project_files(
        project_dir=project_dir, selected_paths=selected_paths
    )
    safe_files, newline_by_path = safe_format_files(files=files, config=config)
    safe_files, rule_fixes, rule_faults = plan_rule_fixes(
        project_dir=project_dir,
        files=safe_files,
        config=config,
        adapter=value_renderer,
        discovered_inputs=discovered_inputs,
        enabled=fix,
    )
    updated_contents, format_faults = _apply_fixes(
        files=safe_files,
        config=config,
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        fixtures_only=fixtures_only,
    )
    format_faults.extend(rule_faults)
    updated_contents: dict[Path, str] = {**safe_files, **updated_contents}
    declined_paths: set[Path] = {fault.file_path for fault in format_faults}
    updated_contents: dict[Path, str] = {
        path: contents for path, contents in updated_contents.items() if path not in declined_paths
    }
    changes: tuple[FormatChange, ...] = persist_changes(
        files=files, updated=updated_contents, newlines=newline_by_path, write=write
    )
    violations: list[LintViolation] = (
        []
        if fixtures_only
        else _lint_final_contents(
            files=files,
            updated_contents=updated_contents,
            config=config,
            project_dir=project_dir,
            value_renderer=value_renderer,
        )
    )
    violations.extend(format_faults)
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
        formatted_files=tuple(change.file_path for change in changes),
        format_changes=changes,
        rule_fixes=finalize_fix_reports(reports=rule_fixes, declined_paths=declined_paths),
        source_texts=final_contents,
    )


def _apply_fixes(
    *,
    files: dict[Path, str],
    config: LintConfig,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs | None,
    fixtures_only: bool,
) -> tuple[dict[Path, str], list[LintViolation]]:
    """Return contents after native header and supported SQL body fixes."""

    updated: dict[Path, str] = (
        FixtureNullAutofix.apply(
            files=files,
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
        )
        if discovered_inputs is not None
        else {}
    )
    if fixtures_only:
        return updated, []
    file_path: Path
    contents: str
    current_files: dict[Path, str] = {
        file_path: updated.get(file_path, contents) for file_path, contents in files.items()
    }
    faults: list[LintViolation] = []
    _ = prepare_native_header_cache(files=current_files)
    for file_path, contents in sorted(current_files.items()):
        native_result: tuple[str, tuple[LintViolation, ...]] = format_native_headers(
            contents=contents,
            file_path=file_path,
            config=config,
        )
        faults.extend(native_result[1])
        if native_result[0] != contents:
            updated[file_path] = native_result[0]
    if not config.native_enabled:
        return reject_unparseable_header_rewrites(
            updated=updated,
            config=config,
            faults=faults,
        )
    current_files = {
        file_path: updated.get(file_path, contents) for file_path, contents in files.items()
    }
    native_formatted, native_faults = format_native_sql_bodies(
        files=current_files,
        config=config,
        project_dir=project_dir,
    )
    faults.extend(native_faults)
    updated.update(native_formatted)
    post_native_files: dict[Path, str] = {
        file_path: updated.get(file_path, contents) for file_path, contents in files.items()
    }
    fixture_formatted: dict[Path, str] = (
        FixtureNullAutofix.apply(
            files=post_native_files,
            project_dir=project_dir,
            discovered_inputs=discovered_inputs,
        )
        if discovered_inputs is not None
        else {}
    )
    if fixture_formatted:
        final_native, final_faults = format_native_sql_bodies(
            files=fixture_formatted,
            config=config,
            project_dir=project_dir,
        )
        faults.extend(final_faults)
        updated.update(fixture_formatted)
        updated.update(final_native)
    return reject_unparseable_header_rewrites(
        updated=updated,
        config=config,
        faults=faults,
    )


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
                description_present_severity=VIOLATION_SEVERITY_WARNING,
            )
        )
    return violations
