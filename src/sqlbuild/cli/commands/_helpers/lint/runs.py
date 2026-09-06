"""Shared helpers for the lint and format CLI commands."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from sqlbuild.cli.commands._helpers.lint.diagnostics import format_lint_diagnostics
from sqlbuild.compiler.discovery.constants import LOCAL_CONFIG_FILENAME
from sqlbuild.lint.constants import (
    ADAPTER_CONFIG_KEY,
    ADAPTER_DIALECT_TRANSLATIONS,
    DEFAULT_MAX_DESCRIPTION_LINES,
    FIX_STATUS_APPLIED,
    FIX_STATUS_SKIPPED,
    LINT_RULE_IGNORE_KEY,
    LINT_RULE_SELECT_KEY,
    LINT_SECTION_KEY,
    MAX_DESCRIPTION_LINES_KEY,
    PROJECT_CONFIG_FILENAME_KEY,
)
from sqlbuild.lint.models import (
    FixRunResult,
    LintConfig,
    LintFixRecord,
    LintRunResult,
    LintViolation,
)
from sqlbuild.presentation.classes.cli_style import CliStyle


def resolve_lint_config(*, project_dir: Path) -> LintConfig:
    """Resolve native lint and format configuration from project settings."""

    max_description_lines: int = DEFAULT_MAX_DESCRIPTION_LINES
    dialect: str = "generic"
    selected_rules: tuple[str, ...] | None = None
    ignored_rules: tuple[str, ...] = ()
    config_file: Path = project_dir / PROJECT_CONFIG_FILENAME_KEY
    if config_file.is_file():
        with config_file.open("rb") as handle:
            payload: dict[str, object] = tomllib.load(handle)
        lint_section: object = payload.get(LINT_SECTION_KEY)
        raw_adapter: object = payload.get(ADAPTER_CONFIG_KEY)
        if isinstance(raw_adapter, str):
            dialect = ADAPTER_DIALECT_TRANSLATIONS.get(raw_adapter, raw_adapter)
        if isinstance(lint_section, dict):
            max_description_lines = _resolve_int(
                section=lint_section,
                key=MAX_DESCRIPTION_LINES_KEY,
                current=max_description_lines,
            )
            selected_rules = _resolve_strings(section=lint_section, key=LINT_RULE_SELECT_KEY)
            ignored_rules = _resolve_strings(section=lint_section, key=LINT_RULE_IGNORE_KEY) or ()
    local_config_file: Path = project_dir / LOCAL_CONFIG_FILENAME
    if local_config_file.is_file():
        with local_config_file.open("rb") as handle:
            local_payload: dict[str, object] = tomllib.load(handle)
        local_adapter: object = local_payload.get(ADAPTER_CONFIG_KEY)
        if isinstance(local_adapter, str):
            dialect = ADAPTER_DIALECT_TRANSLATIONS.get(local_adapter, local_adapter)
    return LintConfig(
        max_description_lines=max_description_lines,
        dialect=dialect,
        enabled_native_rules=selected_rules,
        ignored_native_rules=ignored_rules,
    )


def prepare_lint_run(*, project_dir: Path) -> tuple[LintConfig, str | None]:
    """Resolve native lint configuration."""

    return resolve_lint_config(project_dir=project_dir), None


def render_lint_result(
    *,
    result: LintRunResult,
    root: Path,
    use_color: bool,
    show_formatted: bool,
    formatted_heading: str = "Formatted files:",
) -> None:
    """Print a lint or format run result to stdout."""

    if show_formatted and result.formatted_files:
        print(formatted_heading)
        formatted_path: Path
        for formatted_path in result.formatted_files:
            print(f"  {formatted_path}")
        print()
    if result.violations:
        print("\n\n".join(format_lint_diagnostics(result=result, root=root, use_color=use_color)))
        print()
    summary: str = (
        f"Completed.  FAULT={len(result.faults)}  WARN={len(result.warnings)}  "
        f"FILES={result.files_checked}"
    )
    print(_styled_summary(summary=summary, result=result, use_color=use_color))


def render_lint_result_json(*, result: LintRunResult) -> None:
    """Print a stable machine-readable lint or format result."""

    print(
        json.dumps(
            {
                "faults": len(result.faults),
                "files_checked": result.files_checked,
                "formatted_files": [str(path) for path in result.formatted_files],
                "violations": [
                    {
                        "code": violation.code,
                        "column": violation.column,
                        "end_column": violation.end_column,
                        "end_line": violation.end_line,
                        "engine": violation.engine,
                        "file": str(violation.file_path),
                        "line": violation.line,
                        "message": violation.message,
                        "remediation": violation.remediation,
                        "severity": violation.severity,
                    }
                    for violation in result.violations
                ],
                "warnings": len(result.warnings),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def render_fix_result(*, result: FixRunResult, root: Path, use_color: bool, preview: bool) -> None:
    """Render applied/skipped repairs followed by remaining diagnostics."""

    style: CliStyle = CliStyle(use_color=use_color)
    for record in result.fixes:
        label: str = f"{record.status}[{record.code}]"
        styled: str = (
            style.success_strong(label)
            if record.status == FIX_STATUS_APPLIED
            else style.warning_strong(label)
        )
        location: str = _relative_path(path=record.file_path, root=root)
        suffix: str = f": {record.reason}" if record.reason is not None else ""
        print(f"{styled}: {location}:{record.line}:{record.column}{suffix}")
    if result.fixes:
        print()
    if result.violations:
        print("\n\n".join(format_lint_diagnostics(result=result, root=root, use_color=use_color)))
        print()
    fixed_count: int = sum(record.status == FIX_STATUS_APPLIED for record in result.fixes)
    skipped_count: int = sum(record.status == FIX_STATUS_SKIPPED for record in result.fixes)
    action: str = "WOULD_FIX" if preview else "FIXED"
    summary: str = (
        f"Completed.  {action}={fixed_count}  SKIPPED={skipped_count}  "
        f"REMAINING={len(result.violations)}  FILES={result.files_checked}"
    )
    if result.violations or (preview and result.changed_files):
        print(style.warning_strong(summary))
    else:
        print(style.success_strong(summary))


def render_fix_result_json(*, result: FixRunResult, preview: bool) -> None:
    """Render a stable machine-readable fix result."""

    print(
        json.dumps(
            {
                "changed_files": [str(path) for path in result.changed_files],
                "files_checked": result.files_checked,
                "fixes": [_fix_record_json(record=record) for record in result.fixes],
                "mode": "check" if preview else "write",
                "remaining": [_violation_json(violation=entry) for entry in result.violations],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _fix_record_json(*, record: LintFixRecord) -> dict[str, object]:
    return {
        "code": record.code,
        "column": record.column,
        "file": str(record.file_path),
        "line": record.line,
        "reason": record.reason,
        "status": record.status,
    }


def _violation_json(*, violation: LintViolation) -> dict[str, object]:
    return {
        "code": violation.code,
        "column": violation.column,
        "end_column": violation.end_column,
        "end_line": violation.end_line,
        "engine": violation.engine,
        "file": str(violation.file_path),
        "fix_unavailable_reason": violation.fix_unavailable_reason,
        "line": violation.line,
        "message": violation.message,
        "remediation": violation.remediation,
        "severity": violation.severity,
    }


def _relative_path(*, path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _styled_summary(*, summary: str, result: LintRunResult, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    if result.faults:
        return style.error_strong(summary)
    if result.warnings:
        return style.warning_strong(summary)
    return style.success_strong(summary)


def _resolve_int(*, section: dict[str, object], key: str, current: int) -> int:
    raw_value: object = section.get(key)
    if isinstance(raw_value, int) and raw_value > 0:
        return raw_value
    return current


def _resolve_strings(*, section: dict[str, object], key: str) -> tuple[str, ...] | None:
    raw_value: object = section.get(key)
    if not isinstance(raw_value, list) or not all(isinstance(item, str) for item in raw_value):
        return None
    return tuple(str(item) for item in raw_value)
