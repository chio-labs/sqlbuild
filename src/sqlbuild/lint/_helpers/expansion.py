"""Prepare authored SQL bodies for linting by expanding them like compile does."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.discovery.main.resolve_adapter import resolve_adapter
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main.expand_sql_with_spans import expand_sql_with_spans
from sqlbuild.compiler.compile.main.sql_expansion_context import build_sql_expansion_context
from sqlbuild.compiler.compile.models import ExpansionSpan, SqlExpansionContext
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint._helpers.sqlbuild_tokens import neutralize_interpolation, sentinel_spans
from sqlbuild.lint.exceptions import ProjectCompileError
from sqlbuild.lint.models import InterpolationSite, LintBody
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)


def build_lint_expansion_context(
    *, project_dir: Path, value_renderer: TypedSqlValueRenderer | None = None
) -> SqlExpansionContext:
    """Build the expansion context, reporting compile failures as lint failures."""

    try:
        effective_renderer: TypedSqlValueRenderer = value_renderer or _resolve_value_renderer(
            project_dir=project_dir
        )
        return build_sql_expansion_context(
            project_dir=project_dir,
            value_renderer=effective_renderer,
        )
    except (AdapterUserError, CompileInputError, DiscoveryError) as error:
        raise ProjectCompileError(
            f"sqb lint checks the SQL your project actually produces, so the project must "
            f"compile first: {error}"
        ) from error


def _resolve_value_renderer(*, project_dir: Path) -> TypedSqlValueRenderer:
    discovered: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=project_dir,
        sql_analysis_enabled_override=False,
    )
    return resolve_adapter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered.project_config,
            local_config=discovered.local_config,
        ),
        project_dir=project_dir,
    )


def prepare_lint_body(
    *,
    file_path: Path,
    contents: str,
    body_start: int,
    body_end: int,
    context: SqlExpansionContext,
) -> LintBody:
    """Expand one authored body and neutralize whatever interpolation remains."""

    authored_body: str = contents[body_start:body_end]
    expanded: str
    expansion_passes: tuple[tuple[ExpansionSpan, ...], ...]
    try:
        expanded, expansion_passes = expand_sql_with_spans(
            sql=authored_body, file_path=file_path, context=context
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
        passes=(*expansion_passes, sentinel_spans(sites=sites)),
    )
