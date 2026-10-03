"""Prepare authored SQL bodies for linting by expanding them like compile does."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.discovery.main.resolve_adapter import resolve_adapter
from sqlbuild.compiler.compile.constants import MACRO_TOKEN
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main.expand_sql_with_spans import expand_sql_with_spans
from sqlbuild.compiler.compile.main.sql_expansion_context import build_sql_expansion_context
from sqlbuild.compiler.compile.models import (
    CompiledSqlExpansion,
    DeclarationScopeBuild,
    ExpansionSpan,
    SqlExpansionContext,
)
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.types import DeclarationKind
from sqlbuild.lint._helpers.headers import lint_body_ranges, lint_file_role
from sqlbuild.lint._helpers.native import external_identifiers_for_headers
from sqlbuild.lint._helpers.native_sql import check_lint_not_stopped
from sqlbuild.lint._helpers.sqlbuild_tokens import (
    neutralize_context_interpolation,
    neutralize_generic_audit_parameters,
    neutralize_interpolation,
    sentinel_spans,
)
from sqlbuild.lint.constants import (
    HEADER_KIND_SCENARIO,
    HEADER_KIND_TEST,
    RELATION_IDENTITY_TEMPLATE,
    TEMPLATE_INTERPOLATION_START,
)
from sqlbuild.lint.exceptions import ProjectCompileError
from sqlbuild.lint.models import (
    ExpandedLintFile,
    HeaderSpan,
    InterpolationSite,
    LintBody,
    LintFileRole,
    PendingLintBody,
    PreparedLintFiles,
)
from sqlbuild.lint.types import NativePreparedSql
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)

_DEPENDENCY_INTRINSIC_PATTERN: re.Pattern[str] = re.compile(
    r"^__(?:ref|source)\s*\(", re.IGNORECASE
)
_KEYED_RELATION_PATTERN: re.Pattern[str] = re.compile(
    r"^__(ref|source|seed)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)$", re.IGNORECASE
)

_CTE_DEFINITION_PATTERN: re.Pattern[str] = re.compile(
    r'(?:\bWITH(?:\s+RECURSIVE)?|,)\s*["`\[]?(?P<name>[A-Za-z_][A-Za-z0-9_]*)'
    r'["`\]]?(?:\s*\([^)]*\))?\s+AS\s*\(',
    re.IGNORECASE | re.DOTALL,
)
_OPAQUE_CTE_PREFIX_PATTERN: re.Pattern[str] = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*\s+AS\s*\(\s*(?:--[^\n]*\n\s*)?$",
    re.IGNORECASE,
)


def _externally_referenced_ctes(
    *,
    expanded: str,
    interpolation_sites: tuple[InterpolationSite, ...],
    pre_expansion_body: str,
    pre_expansion_sites: tuple[InterpolationSite, ...],
) -> tuple[str, ...]:
    names: set[str] = {
        match.group("name").lower() for match in _CTE_DEFINITION_PATTERN.finditer(expanded)
    }
    referenced: set[str] = set()
    for name in names:
        for site in interpolation_sites:
            if re.search(rf"\b{re.escape(name)}\b", site.original_text, re.IGNORECASE) is not None:
                referenced.add(name)
                break
    for site in pre_expansion_sites:
        prefix: str = pre_expansion_body[: site.neutralized_start]
        if _OPAQUE_CTE_PREFIX_PATTERN.search(prefix) is None:
            continue
        referenced.update(
            match.group("name").lower() for match in _CTE_DEFINITION_PATTERN.finditer(prefix)
        )
    return tuple(sorted(referenced.intersection(names)))


def build_lint_expansion_context(
    *,
    project_dir: Path,
    value_renderer: TypedSqlValueRenderer | None = None,
    discovered_inputs: DiscoveredProjectInputs | None = None,
    declaration_scope: DeclarationScopeBuild | None = None,
    static_declaration_scope: DeclarationScopeBuild | None = None,
) -> SqlExpansionContext:
    """Build the expansion context, reporting compile failures as lint failures."""

    try:
        effective_discovered_inputs: DiscoveredProjectInputs = (
            discovered_inputs
            if discovered_inputs is not None
            else discover_project_inputs(
                project_dir=project_dir,
                sql_analysis_enabled_override=False,
                extract_output_column_locations=False,
            )
        )
        effective_renderer: TypedSqlValueRenderer = value_renderer or _resolve_value_renderer(
            project_dir=project_dir,
            discovered_inputs=effective_discovered_inputs,
        )
        return build_sql_expansion_context(
            project_dir=project_dir,
            discovered_inputs=effective_discovered_inputs,
            value_renderer=effective_renderer,
            declaration_scope=declaration_scope,
            static_declaration_scope=static_declaration_scope,
        )
    except (AdapterUserError, CompileInputError, DiscoveryError) as error:
        raise ProjectCompileError(
            "compiler-integrated Rules check the SQL your project actually produces, "
            "so the project must "
            f"compile first: {error}"
        ) from error


def _resolve_value_renderer(
    *, project_dir: Path, discovered_inputs: DiscoveredProjectInputs
) -> TypedSqlValueRenderer:
    return resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=project_dir,
    )


def prepare_lint_body(
    *,
    role: LintFileRole,
    file_path: Path,
    contents: str,
    body_range: tuple[int, int],
    context: SqlExpansionContext,
    dialect: str,
    external_identifiers: tuple[str, ...] = (),
    allows_ceremonial_select: bool = False,
    allows_dynamic_output_star: bool = False,
    compiled_expansion: CompiledSqlExpansion | None = None,
) -> LintBody:
    """Expand one authored body and neutralize whatever interpolation remains."""

    pending: PendingLintBody = expand_lint_body(
        role=role,
        file_path=file_path,
        contents=contents,
        body_range=body_range,
        context=context,
        dialect=dialect,
        external_identifiers=external_identifiers,
        allows_ceremonial_select=allows_ceremonial_select,
        allows_dynamic_output_star=allows_dynamic_output_star,
        compiled_expansion=compiled_expansion,
    )
    return finish_lint_body(
        pending=pending, prepared=_native.prepare_lint_sql(pending.request), dialect=dialect
    )


def expand_lint_body(
    *,
    role: LintFileRole,
    file_path: Path,
    contents: str,
    body_range: tuple[int, int],
    context: SqlExpansionContext,
    dialect: str,
    external_identifiers: tuple[str, ...] = (),
    allows_ceremonial_select: bool = False,
    allows_dynamic_output_star: bool = False,
    compiled_expansion: CompiledSqlExpansion | None = None,
) -> PendingLintBody:
    """Expand one authored body like compile does, leaving its native preparation pending."""

    body_start: int
    body_end: int
    body_start, body_end = body_range
    authored_body: str = contents[body_start:body_end]
    pre_expansion_sites: tuple[InterpolationSite, ...] = ()
    expansion_input: str = authored_body
    if _is_generic_audit_path(role=role):
        expansion_input, pre_expansion_sites = neutralize_generic_audit_parameters(
            body=authored_body
        )
    elif _is_sql_hook_path(role=role):
        expansion_input, pre_expansion_sites = neutralize_context_interpolation(body=authored_body)
    expanded: str
    expansion_passes: tuple[tuple[ExpansionSpan, ...], ...]
    try:
        if (
            compiled_expansion is not None
            and authored_body.strip() == compiled_expansion.authored_sql
        ):
            body_start += len(authored_body) - len(authored_body.lstrip())
            body_end = body_start + len(compiled_expansion.authored_sql)
            expansion_input = compiled_expansion.authored_sql
            expanded = compiled_expansion.expanded_sql
            expansion_passes = compiled_expansion.passes
        elif (
            MACRO_TOKEN not in expansion_input
            and TEMPLATE_INTERPOLATION_START not in expansion_input
        ):
            expanded = expansion_input
            expansion_passes = ()
        else:
            expanded, expansion_passes = expand_sql_with_spans(
                sql=expansion_input, file_path=file_path, context=context
            )
    except CompileInputError as error:
        raise ProjectCompileError(
            f"{file_path} could not be expanded, so its SQL cannot be linted: {error}"
        ) from error
    return PendingLintBody(
        file_path=file_path,
        body_start=body_start,
        body_end=body_end,
        expansion_input=expansion_input,
        expanded=expanded,
        expansion_passes=expansion_passes,
        pre_expansion_sites=pre_expansion_sites,
        external_identifiers=external_identifiers,
        allows_ceremonial_select=allows_ceremonial_select,
        allows_dynamic_output_star=allows_dynamic_output_star,
        allows_empty_fixture_star=False,
        request={
            "expanded": expanded,
            "before_expansion": expansion_input,
            "prior_sites": [site.neutralized_start for site in pre_expansion_sites],
            "dialect": dialect,
        },
    )


def prepare_lint_sql_batch(
    pending: tuple[PendingLintBody, ...],
) -> tuple[NativePreparedSql | None, ...]:
    """Prepare pending bodies in one GIL-free native call; failures re-raise per body, in order."""

    if not pending:
        return ()
    results: list[tuple[bool, NativePreparedSql | None]] = _native.prepare_lint_sql_batch(
        [body.request for body in pending]
    )
    return tuple(
        prepared if succeeded else _native.prepare_lint_sql(body.request)
        for body, (succeeded, prepared) in zip(pending, results, strict=True)
    )


def finish_lint_body(
    *, pending: PendingLintBody, prepared: NativePreparedSql | None, dialect: str
) -> LintBody:
    """Build the lint body from one body's native preparation, or the Python fallback."""

    expanded: str = pending.expanded
    neutralized: str
    sites: tuple[InterpolationSite, ...]
    if prepared is None:
        neutralized, sites = neutralize_interpolation(body=expanded, dialect=dialect)
        externally_referenced_ctes: tuple[str, ...] = _externally_referenced_ctes(
            expanded=expanded,
            interpolation_sites=sites,
            pre_expansion_body=pending.expansion_input,
            pre_expansion_sites=pending.pre_expansion_sites,
        )
    else:
        neutralized = prepared[0]
        sites = tuple(InterpolationSite(*site) for site in prepared[1])
        externally_referenced_ctes = tuple(prepared[2])
    dependency_identifiers: tuple[str, ...] = tuple(
        site.sentinel
        for site in sites
        if _DEPENDENCY_INTRINSIC_PATTERN.match(site.original_text) is not None
    )
    return LintBody(
        file_path=pending.file_path,
        body_start=pending.body_start,
        body_end=pending.body_end,
        lint_text=neutralized,
        passes=(
            sentinel_spans(sites=pending.pre_expansion_sites),
            *pending.expansion_passes,
            sentinel_spans(sites=sites),
        ),
        external_identifiers=pending.external_identifiers,
        dependency_identifiers=dependency_identifiers,
        externally_referenced_ctes=externally_referenced_ctes,
        allows_ceremonial_select=pending.allows_ceremonial_select,
        allows_dynamic_output_star=pending.allows_dynamic_output_star,
        allows_empty_fixture_star=pending.allows_empty_fixture_star,
        dependency_relations=tuple(
            (
                site.sentinel,
                RELATION_IDENTITY_TEMPLATE.format(kind=match.group(1).lower(), name=match.group(2)),
            )
            for site in sites
            if (match := _KEYED_RELATION_PATTERN.match(site.original_text)) is not None
        ),
    )


def _is_generic_audit_path(*, role: LintFileRole) -> bool:
    """Return whether a lint input is an authored generic-audit definition."""

    return role.in_project and role.declaration_kind is DeclarationKind.AUDIT


def _is_sql_hook_path(*, role: LintFileRole) -> bool:
    return role.in_hook_directory or (
        role.in_project and role.declaration_kind is DeclarationKind.SQL_HOOK
    )


def expand_file_bodies(
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
) -> ExpandedLintFile:
    """Expand one file's bodies up to the first body that cannot be expanded."""

    check_lint_not_stopped()
    bodies: list[PendingLintBody] = []
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
                    expand_lint_body(
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
        return ExpandedLintFile(file_path=file_path, bodies=tuple(bodies), failure=error)
    return ExpandedLintFile(file_path=file_path, bodies=tuple(bodies), failure=None)


def prepare_expanded_files(
    *, expanded_files: tuple[ExpandedLintFile, ...], dialect: str, skip_unexpandable: bool
) -> PreparedLintFiles:
    """Prepare every expanded body natively at once, then report failures in file order."""

    check_lint_not_stopped()
    pending: list[PendingLintBody] = []
    for expanded in expanded_files:
        pending.extend(expanded.bodies)
    prepared: tuple[NativePreparedSql | None, ...] = prepare_lint_sql_batch(tuple(pending))
    bodies: list[LintBody] = []
    unexpandable: dict[Path, str] = {}
    position: int = 0
    for expanded in expanded_files:
        file_bodies: list[LintBody] = []
        for body in expanded.bodies:
            file_bodies.append(
                finish_lint_body(pending=body, prepared=prepared[position], dialect=dialect)
            )
            position += 1
        if expanded.failure is None:
            bodies.extend(file_bodies)
        elif skip_unexpandable:
            unexpandable[expanded.file_path] = str(expanded.failure).removeprefix(
                f"{expanded.file_path} "
            )
        else:
            raise expanded.failure
    return PreparedLintFiles(bodies=tuple(bodies), unexpandable=unexpandable)
