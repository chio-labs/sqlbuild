"""Prepare authored SQL bodies for linting by expanding them like compile does."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.discovery.main.resolve_adapter import resolve_adapter
from sqlbuild.compiler.compile.constants import (
    AUDIT_DIRECTORY_NAME,
    GENERIC_AUDIT_DIRECTORY_NAME,
    HOOK_DIRECTORY_NAME,
    MACRO_TOKEN,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main.expand_sql_with_spans import expand_sql_with_spans
from sqlbuild.compiler.compile.main.sql_expansion_context import build_sql_expansion_context
from sqlbuild.compiler.compile.models import ExpansionSpan, SqlExpansionContext
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint._helpers.sqlbuild_tokens import (
    neutralize_context_interpolation,
    neutralize_generic_audit_parameters,
    neutralize_interpolation,
    sentinel_spans,
)
from sqlbuild.lint.constants import TEMPLATE_INTERPOLATION_START
from sqlbuild.lint.exceptions import ProjectCompileError
from sqlbuild.lint.models import InterpolationSite, LintBody
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def build_lint_expansion_context(
    *,
    project_dir: Path,
    value_renderer: TypedSqlValueRenderer | None = None,
    discovered_inputs: DiscoveredProjectInputs | None = None,
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
        )
    except (AdapterUserError, CompileInputError, DiscoveryError) as error:
        raise ProjectCompileError(
            f"sqb lint checks the SQL your project actually produces, so the project must "
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
    project_dir: Path,
    file_path: Path,
    contents: str,
    body_start: int,
    body_end: int,
    context: SqlExpansionContext,
) -> LintBody:
    """Expand one authored body and neutralize whatever interpolation remains."""

    authored_body: str = contents[body_start:body_end]
    pre_expansion_sites: tuple[InterpolationSite, ...] = ()
    expansion_input: str = authored_body
    if _is_generic_audit_path(file_path=file_path, project_dir=project_dir):
        expansion_input, pre_expansion_sites = neutralize_generic_audit_parameters(
            body=authored_body
        )
    elif file_path.is_relative_to(project_dir / HOOK_DIRECTORY_NAME):
        expansion_input, pre_expansion_sites = neutralize_context_interpolation(body=authored_body)
    expanded: str
    expansion_passes: tuple[tuple[ExpansionSpan, ...], ...]
    try:
        if (
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
    neutralized: str
    sites: tuple[InterpolationSite, ...]
    neutralized, sites = neutralize_interpolation(body=expanded)
    return LintBody(
        file_path=file_path,
        body_start=body_start,
        body_end=body_end,
        lint_text=neutralized,
        passes=(
            sentinel_spans(sites=pre_expansion_sites),
            *expansion_passes,
            sentinel_spans(sites=sites),
        ),
    )


def _is_generic_audit_path(*, file_path: Path, project_dir: Path) -> bool:
    """Return whether a lint input is an authored generic-audit definition."""

    return file_path.is_relative_to(
        project_dir / AUDIT_DIRECTORY_NAME / GENERIC_AUDIT_DIRECTORY_NAME
    )
