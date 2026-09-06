"""Shared helpers for the lint and format CLI commands."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from sqlbuild.compiler.discovery.constants import LOCAL_CONFIG_FILENAME
from sqlbuild.lint.constants import (
    ADAPTER_CONFIG_KEY,
    ADAPTER_DIALECT_TRANSLATIONS,
    DEFAULT_MAX_DESCRIPTION_LINES,
    LINT_SECTION_KEY,
    MAX_DESCRIPTION_LINES_KEY,
    PROJECT_CONFIG_FILENAME_KEY,
)
from sqlbuild.lint.models import LintConfig, LintRunResult


def resolve_lint_config(*, project_dir: Path) -> LintConfig:
    """Resolve native lint and format configuration from project settings."""

    max_description_lines: int = DEFAULT_MAX_DESCRIPTION_LINES
    dialect: str = "generic"
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
    )


def prepare_lint_run(*, project_dir: Path) -> tuple[LintConfig, str | None]:
    """Resolve native lint configuration."""

    return resolve_lint_config(project_dir=project_dir), None


def render_lint_result(
    *,
    result: LintRunResult,
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
        _print_violations(result=result)
    print(
        f"Completed.  FAULT={len(result.faults)}  WARN={len(result.warnings)}  "
        f"FILES={result.files_checked}"
    )


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
                        "engine": violation.engine,
                        "file": str(violation.file_path),
                        "line": violation.line,
                        "message": violation.message,
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


def _print_violations(*, result: LintRunResult) -> None:
    current_file: Path | None = None
    violation: object
    for violation in result.violations:
        if violation.file_path != current_file:
            current_file = violation.file_path
            print(f"{current_file}")
        print(
            f"  {violation.line}:{violation.column}  "
            f"{violation.engine}  {violation.code}  {violation.message}"
        )
    print()


def _resolve_int(*, section: dict[str, object], key: str, current: int) -> int:
    raw_value: object = section.get(key)
    if isinstance(raw_value, int) and raw_value > 0:
        return raw_value
    return current
