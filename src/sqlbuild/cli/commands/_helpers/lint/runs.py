"""Shared helpers for the lint and format CLI commands."""

from __future__ import annotations

import tomllib
from pathlib import Path

from sqlbuild.cli.commands._helpers.runtime.adapters import resolve_adapter
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint.constants import (
    DEFAULT_MAX_DESCRIPTION_LINES,
    DEFAULT_SQRUFF_CONFIG_PATH,
    LINT_SECTION_KEY,
    MAX_DESCRIPTION_LINES_KEY,
    PROJECT_CONFIG_FILENAME_KEY,
    SQRUFF_CONFIG_PATH_KEY,
    SQRUFF_ENABLED_KEY,
)
from sqlbuild.lint.main.ensure_config import ensure_sqruff_config
from sqlbuild.lint.models import LintConfig, LintRunResult
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def resolve_lint_config(*, project_dir: Path, no_sqruff: bool) -> LintConfig:
    """Resolve the effective lint config from project settings and CLI flags."""

    sqruff_enabled: bool = not no_sqruff
    sqruff_config_path: str = DEFAULT_SQRUFF_CONFIG_PATH
    max_description_lines: int = DEFAULT_MAX_DESCRIPTION_LINES
    config_file: Path = project_dir / PROJECT_CONFIG_FILENAME_KEY
    if config_file.is_file():
        with config_file.open("rb") as handle:
            payload: dict[str, object] = tomllib.load(handle)
        lint_section: object = payload.get(LINT_SECTION_KEY)
        if isinstance(lint_section, dict):
            sqruff_enabled = _resolve_bool(
                section=lint_section,
                key=SQRUFF_ENABLED_KEY,
                current=sqruff_enabled,
            )
            sqruff_config_path = _resolve_str(
                section=lint_section,
                key=SQRUFF_CONFIG_PATH_KEY,
                current=sqruff_config_path,
            )
            max_description_lines = _resolve_int(
                section=lint_section,
                key=MAX_DESCRIPTION_LINES_KEY,
                current=max_description_lines,
            )
    return LintConfig(
        sqruff_enabled=sqruff_enabled,
        sqruff_config_path=sqruff_config_path,
        max_description_lines=max_description_lines,
    )


def prepare_lint_run(*, project_dir: Path, no_sqruff: bool) -> tuple[LintConfig, str | None]:
    """Resolve config, scaffold a missing sqruff config, and return any drift warning."""

    config: LintConfig = resolve_lint_config(project_dir=project_dir, no_sqruff=no_sqruff)
    warning: str | None = ensure_sqruff_config(
        project_dir=project_dir,
        config_path=config.sqruff_config_path,
        sqruff_enabled=config.sqruff_enabled,
    )
    return config, warning


def resolve_lint_value_renderer(
    *, project_dir: Path, config: LintConfig
) -> TypedSqlValueRenderer | None:
    """Resolve typed SQL rendering only when expanded-SQL lint is enabled."""

    if not config.sqruff_enabled:
        return None
    discovered: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=project_dir,
        sql_analysis_enabled_override=False,
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered.project_config,
        local_config=discovered.local_config,
    )
    return resolve_adapter(adapter_name=adapter_name, project_dir=project_dir)


def render_lint_result(*, result: LintRunResult, show_formatted: bool) -> None:
    """Print a lint or format run result to stdout."""

    if show_formatted and result.formatted_files:
        print("Formatted files:")
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


def _resolve_bool(*, section: dict[str, object], key: str, current: bool) -> bool:
    raw_value: object = section.get(key)
    if isinstance(raw_value, bool):
        return current and raw_value
    return current


def _resolve_str(*, section: dict[str, object], key: str, current: str) -> str:
    raw_value: object = section.get(key)
    if isinstance(raw_value, str) and raw_value:
        return raw_value
    return current


def _resolve_int(*, section: dict[str, object], key: str, current: int) -> int:
    raw_value: object = section.get(key)
    if isinstance(raw_value, int) and raw_value > 0:
        return raw_value
    return current
