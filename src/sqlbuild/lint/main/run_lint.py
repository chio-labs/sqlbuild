"""Run the lint pass over a SQLBuild project."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile.constants import MODEL_DIRECTORY_NAME
from sqlbuild.compiler.compile.models import CompiledSqlExpansion, SqlExpansionContext
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.constants import (
    DECLARATION_GROUP_DIRECTORY,
    INHERITED_DECLARATION_DIRECTORIES,
    LOCAL_DECLARATION_DIRECTORIES,
)
from sqlbuild.lint._helpers.expansion import build_lint_expansion_context, prepare_lint_body
from sqlbuild.lint._helpers.headers import lint_body_ranges, lint_file_role, scan_headers
from sqlbuild.lint._helpers.native import external_identifiers_for_headers, lint_native_headers
from sqlbuild.lint._helpers.native_sql import run_native_sql_lint
from sqlbuild.lint._helpers.project_files import collect_project_files, sort_violations
from sqlbuild.lint._helpers.suppressions import apply_suppressions
from sqlbuild.lint.constants import HEADER_KIND_SCENARIO, HEADER_KIND_TEST
from sqlbuild.lint.exceptions import ProjectCompileError
from sqlbuild.lint.models import (
    HeaderSpan,
    LintBody,
    LintConfig,
    LintFileRole,
    LintRunResult,
    LintViolation,
)


def run_lint(
    *,
    project_dir: Path,
    config: LintConfig,
    value_renderer: TypedSqlValueRenderer | None = None,
    selected_paths: frozenset[Path] | None = None,
    discovered_inputs: DiscoveredProjectInputs | None = None,
    dynamic_output_paths: frozenset[Path] = frozenset(),
    compiled_expansions: dict[Path, CompiledSqlExpansion] | None = None,
    expansion_context: SqlExpansionContext | None = None,
    source_files: dict[Path, str] | None = None,
    skip_unexpandable: bool = False,
) -> LintRunResult:
    """Lint all DSL files without modifying anything; optionally skip unexpandable SQL."""

    files: dict[Path, str] = collect_project_files(
        project_dir=project_dir, selected_paths=selected_paths, source_files=source_files
    )
    violations: list[LintViolation] = []
    bodies: list[LintBody] = []
    unexpandable: dict[Path, str] = {}
    context: SqlExpansionContext | None = expansion_context or _expansion_context(
        project_dir=project_dir,
        native_enabled=config.native_enabled,
        value_renderer=value_renderer,
        discovered_inputs=discovered_inputs,
    )
    file_path: Path
    contents: str
    for file_path, contents in sorted(files.items()):
        relative_path: Path = file_path.relative_to(project_dir)
        relative_parts: tuple[str, ...] = relative_path.parts
        declaration_directories: frozenset[str] = (
            INHERITED_DECLARATION_DIRECTORIES
            | LOCAL_DECLARATION_DIRECTORIES
            | {DECLARATION_GROUP_DIRECTORY}
        )
        headers: tuple[HeaderSpan, ...] = scan_headers(
            contents=contents,
            first_only=(
                relative_parts[:1] == (MODEL_DIRECTORY_NAME,)
                and not declaration_directories.intersection(relative_parts[1:-1])
            ),
        )
        if config.header_rules_enabled:
            violations.extend(
                lint_native_headers(
                    contents=contents,
                    file_path=file_path,
                    headers=headers,
                    config=config,
                )
            )
        if context is None:
            continue
        prepared: tuple[LintBody, ...] | str = _prepared_bodies(
            file_path=file_path,
            contents=contents,
            headers=headers,
            context=context,
            dialect=config.dialect,
            project_dir=project_dir,
            relative_path=relative_path,
            dynamic_output_paths=dynamic_output_paths,
            compiled_expansions=compiled_expansions,
            skip_unexpandable=skip_unexpandable,
        )
        if isinstance(prepared, str):
            unexpandable[file_path] = prepared
        else:
            bodies.extend(prepared)

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
        unexpandable=unexpandable,
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
    dialect: str,
    project_dir: Path,
    relative_path: Path,
    dynamic_output_paths: frozenset[Path],
    compiled_expansions: dict[Path, CompiledSqlExpansion] | None,
    skip_unexpandable: bool,
) -> tuple[LintBody, ...] | str:
    """Prepared bodies of one file, or the reason its SQL cannot be expanded when skipping."""

    bodies: list[LintBody] = []
    role: LintFileRole = lint_file_role(
        file_path=file_path, project_dir=project_dir, relative_path=relative_path
    )
    allows_dynamic_output_star: bool = (
        bool(dynamic_output_paths) and file_path.resolve() in dynamic_output_paths
    )
    compiled_expansion: CompiledSqlExpansion | None = (compiled_expansions or {}).get(file_path)
    external_identifiers: tuple[str, ...] = external_identifiers_for_headers(
        contents=contents, headers=headers
    )
    allows_ceremonial_select: bool = any(
        header.kind in {HEADER_KIND_TEST, HEADER_KIND_SCENARIO} for header in headers
    )
    allows_empty_fixture_star: bool = any(header.kind == HEADER_KIND_TEST for header in headers)
    body_start: int
    body_end: int
    try:
        for body_start, body_end in lint_body_ranges(
            contents=contents,
            headers=headers,
            file_path=file_path,
            project_dir=project_dir,
            role=role,
        ):
            bodies.append(
                replace(
                    prepare_lint_body(
                        role=role,
                        file_path=file_path,
                        contents=contents,
                        body_range=(body_start, body_end),
                        context=context,
                        dialect=dialect,
                        external_identifiers=external_identifiers,
                        allows_ceremonial_select=allows_ceremonial_select,
                        allows_dynamic_output_star=allows_dynamic_output_star,
                        compiled_expansion=compiled_expansion,
                    ),
                    allows_empty_fixture_star=allows_empty_fixture_star,
                )
            )
    except ProjectCompileError as error:
        if not skip_unexpandable:
            raise
        return str(error).removeprefix(f"{file_path} ")
    return tuple(bodies)
