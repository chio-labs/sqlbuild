"""Scope output test builders."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.scopes.main.preview_scope_move import preview_scope_move
from sqlbuild.compiler.scopes.main.query_scope_report import query_scope_report
from sqlbuild.compiler.scopes.models import ScopeLookup, ScopeReport, ScopeReportFilters
from tests.unit.src.sqlbuild.compiler.scopes.helpers import report_scope_lookup


def orders_move_report() -> ScopeReport:
    """Return the orders report with a move preview into models/marts."""

    lookup: ScopeLookup = report_scope_lookup()
    report: ScopeReport = query_scope_report(
        lookup=lookup, target="model:orders", at=None, directory=False, filters=ScopeReportFilters()
    )
    move, diagnostics = preview_scope_move(
        lookup=lookup, resource="model:orders", destination="models/marts/orders.sql"
    )
    return replace(report, move_preview=move, diagnostics=(*report.diagnostics, *diagnostics))
