"""Prepare authored SQL bodies for linting by expanding them like compile does."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main.expand_sql_with_spans import expand_sql_with_spans
from sqlbuild.compiler.compile.main.sql_expansion_context import build_sql_expansion_context
from sqlbuild.compiler.compile.models import ExpansionSpan, SqlExpansionContext
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.lint._helpers.sqlbuild_tokens import neutralize_interpolation, sentinel_spans
from sqlbuild.lint.exceptions import ProjectCompileError
from sqlbuild.lint.models import InterpolationSite, LintBody


def build_lint_expansion_context(*, project_dir: Path) -> SqlExpansionContext:
    """Build the expansion context, reporting compile failures as lint failures."""

    try:
        return build_sql_expansion_context(project_dir=project_dir)
    except (CompileInputError, DiscoveryError) as error:
        raise ProjectCompileError(
            f"sqb lint checks the SQL your project actually produces, so the project must "
            f"compile first: {error}"
        ) from error


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
