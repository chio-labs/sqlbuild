"""Offline declaration-scope inspection command."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands._helpers.scope.output import render_scope_result
from sqlbuild.cli.commands.models import ScopeCommandRequest
from sqlbuild.cli.commands.types import ScopeIndexLoader
from sqlbuild.compiler.scopes.main.browse_scope_folders import browse_scope_folders
from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.main.explain_scope_declaration import explain_scope_declaration
from sqlbuild.compiler.scopes.main.list_scope_declarations import list_scope_declarations
from sqlbuild.compiler.scopes.main.load_or_build_scope_index import load_or_build_scope_index
from sqlbuild.compiler.scopes.main.preview_scope_move import preview_scope_move
from sqlbuild.compiler.scopes.main.query_scope_report import query_scope_report
from sqlbuild.compiler.scopes.main.serialize_scope_report import serialize_scope_report
from sqlbuild.compiler.scopes.models import (
    ScopeBrowseResult,
    ScopeDiagnostic,
    ScopeIndex,
    ScopeListResult,
    ScopeLookup,
    ScopeReport,
    ScopeReportFilters,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, DiagnosticSeverity


def run_scope_command(
    *,
    request: ScopeCommandRequest,
    load_scope_index: ScopeIndexLoader = load_or_build_scope_index,
    output_stream: TextIO | None = None,
) -> int:
    """Load offline compiler facts, run one pure query, and present its result."""

    project_dir: Path = request.project_dir if request.project_dir is not None else Path.cwd()
    index: ScopeIndex = load_scope_index(project_dir=project_dir, no_cache=request.no_cache)
    lookup: ScopeLookup = build_scope_lookup(index=index)
    filters: ScopeReportFilters = ScopeReportFilters(
        include_nearby=request.include_nearby,
        defined_under=request.defined_under,
        kinds=tuple(DeclarationKind(kind) for kind in request.kinds),
        glob=request.match,
        used_only=request.used_only,
        dependency_depth=request.dependency_depth,
        cursor=request.after,
        page_size=request.page_size,
        nearby_depth=request.nearby_depth,
        globals=request.globals,
    )
    result: ScopeReport | ScopeBrowseResult | ScopeListResult
    if request.browse is not None:
        result = browse_scope_folders(
            lookup=lookup,
            folder=request.browse,
            target=request.target,
            target_is_prospective=request.at is not None,
        )
    elif request.list_path is not None:
        result = list_scope_declarations(
            lookup=lookup,
            folder=request.list_path,
            filters=filters,
            target=request.target,
            target_is_prospective=request.at is not None,
        )
    else:
        directory: bool = request.at is not None and request.at.endswith(("/", "\\"))
        report: ScopeReport = query_scope_report(
            lookup=lookup,
            target=request.target,
            at=request.at,
            directory=directory,
            filters=filters,
        )
        if request.explain is not None:
            explanation, diagnostics = explain_scope_declaration(
                lookup=lookup,
                declaration=request.explain,
                target=request.target,
                at=request.at,
                directory=directory,
            )
            report = replace(
                report,
                explanation=explanation,
                diagnostics=(*report.diagnostics, *diagnostics),
                complete=report.complete and explanation.complete,
            )
        if request.as_path is not None:
            move, diagnostics = preview_scope_move(
                lookup=lookup, resource=request.target or "", destination=request.as_path
            )
            report = replace(
                report,
                move_preview=move,
                diagnostics=(*report.diagnostics, *diagnostics),
                complete=report.complete and move is not None and move.complete,
            )
        result = report
    stream: TextIO = output_stream if output_stream is not None else sys.stdout
    output: str = (
        serialize_scope_report(report=result)
        if request.json_output
        else render_scope_result(result=result, request=request)
    )
    stream.write(output)
    return 1 if _failed(result=result) else 0


def _failed(*, result: ScopeReport | ScopeBrowseResult | ScopeListResult) -> bool:
    if isinstance(result, ScopeReport):
        complete: bool = result.complete
        diagnostics: tuple[ScopeDiagnostic, ...] = result.diagnostics
    elif isinstance(result, ScopeBrowseResult):
        complete = result.complete
        diagnostics = result.diagnostics
    else:
        complete = result.section.complete
        diagnostics = result.diagnostics
    return not complete or any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics)
