"""Run the lint pass over a SQLBuild project."""

from __future__ import annotations

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
from sqlbuild.lint._helpers.expansion import (
    build_lint_expansion_context,
    expand_file_bodies,
    prepare_expanded_files,
)
from sqlbuild.lint._helpers.headers import scan_headers
from sqlbuild.lint._helpers.native import lint_native_headers
from sqlbuild.lint._helpers.native_sql import run_native_sql_lint
from sqlbuild.lint._helpers.project_files import collect_project_files, sort_violations
from sqlbuild.lint._helpers.suppressions import apply_suppressions
from sqlbuild.lint.models import (
    ExpandedLintFile,
    HeaderSpan,
    LintBody,
    LintConfig,
    LintRunResult,
    LintViolation,
    PreparedLintFiles,
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
    context: SqlExpansionContext | None = expansion_context or _expansion_context(
        project_dir=project_dir,
        native_enabled=config.native_enabled,
        value_renderer=value_renderer,
        discovered_inputs=discovered_inputs,
    )
    expanded_files: list[ExpandedLintFile] = []
    failure: Exception | None = None
    file_path: Path
    contents: str
    for file_path, contents in sorted(files.items()):
        try:
            header_violations: tuple[LintViolation, ...]
            expanded: ExpandedLintFile | None
            header_violations, expanded = _scan_file(
                file_path=file_path,
                contents=contents,
                project_dir=project_dir,
                config=config,
                context=context,
                dynamic_output_paths=dynamic_output_paths,
                compiled_expansions=compiled_expansions,
            )
        except Exception as error:
            failure = error
            break
        violations.extend(header_violations)
        if expanded is None:
            continue
        expanded_files.append(expanded)
        if expanded.failure is not None and not skip_unexpandable:
            break
    prepared: PreparedLintFiles = prepare_expanded_files(
        expanded_files=tuple(expanded_files),
        dialect=config.dialect,
        skip_unexpandable=skip_unexpandable,
    )
    if failure is not None:
        raise failure
    bodies: tuple[LintBody, ...] = prepared.bodies
    unexpandable: dict[Path, str] = prepared.unexpandable

    if bodies and config.native_enabled:
        native_violations: dict[Path, tuple[LintViolation, ...]] = run_native_sql_lint(
            bodies=bodies,
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


def _scan_file(
    *,
    file_path: Path,
    contents: str,
    project_dir: Path,
    config: LintConfig,
    context: SqlExpansionContext | None,
    dynamic_output_paths: frozenset[Path],
    compiled_expansions: dict[Path, CompiledSqlExpansion] | None,
) -> tuple[tuple[LintViolation, ...], ExpandedLintFile | None]:
    """Header violations of one file and, when expanding, its bodies awaiting preparation."""

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
    header_violations: tuple[LintViolation, ...] = (
        tuple(
            lint_native_headers(
                contents=contents,
                file_path=file_path,
                headers=headers,
                config=config,
            )
        )
        if config.header_rules_enabled
        else ()
    )
    if context is None:
        return header_violations, None
    return header_violations, expand_file_bodies(
        file_path=file_path,
        contents=contents,
        headers=headers,
        context=context,
        dialect=config.dialect,
        project_dir=project_dir,
        relative_path=relative_path,
        dynamic_output_paths=dynamic_output_paths,
        compiled_expansions=compiled_expansions,
    )
