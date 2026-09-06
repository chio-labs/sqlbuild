"""Run the lint pass over a SQLBuild project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.constants import MODEL_DIRECTORY_NAME
from sqlbuild.compiler.compile.models import SqlExpansionContext
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.constants import (
    INHERITED_DECLARATION_DIRECTORIES,
    LOCAL_DECLARATION_DIRECTORIES,
)
from sqlbuild.lint._helpers.expansion import build_lint_expansion_context, prepare_lint_body
from sqlbuild.lint._helpers.headers import lint_body_ranges, scan_headers
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
    discovered_inputs: DiscoveredProjectInputs | None = None,
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
        discovered_inputs=discovered_inputs,
    )
    file_path: Path
    contents: str
    for file_path, contents in sorted(files.items()):
        relative_parts: tuple[str, ...] = file_path.relative_to(project_dir).parts
        declaration_directories: frozenset[str] = (
            INHERITED_DECLARATION_DIRECTORIES | LOCAL_DECLARATION_DIRECTORIES
        )
        headers: tuple[HeaderSpan, ...] = scan_headers(
            contents=contents,
            first_only=(
                relative_parts[:1] == (MODEL_DIRECTORY_NAME,)
                and not declaration_directories.intersection(relative_parts[1:-1])
            ),
        )
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
                    project_dir=project_dir,
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
        source_texts=files,
    )


def _expansion_context(
    *,
    project_dir: Path,
    native_enabled: bool,
    value_renderer: TypedSqlValueRenderer | None,
    discovered_inputs: DiscoveredProjectInputs | None,
) -> SqlExpansionContext | None:
    if not native_enabled:
        return None
    return build_lint_expansion_context(
        project_dir=project_dir,
        value_renderer=value_renderer,
        discovered_inputs=discovered_inputs,
    )


def _prepared_bodies(
    *,
    file_path: Path,
    contents: str,
    headers: tuple[HeaderSpan, ...],
    context: SqlExpansionContext,
    project_dir: Path,
) -> tuple[LintBody, ...]:
    bodies: list[LintBody] = []
    body_start: int
    body_end: int
    for body_start, body_end in lint_body_ranges(
        contents=contents,
        headers=headers,
        file_path=file_path,
        project_dir=project_dir,
    ):
        bodies.append(
            prepare_lint_body(
                project_dir=project_dir,
                file_path=file_path,
                contents=contents,
                body_start=body_start,
                body_end=body_end,
                context=context,
            )
        )
    return tuple(bodies)
