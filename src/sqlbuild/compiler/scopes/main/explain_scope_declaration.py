"""Public detailed declaration explanation operation."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.report_query import (
    _prospective_resource,
    explain_declaration,
)
from sqlbuild.compiler.scopes._helpers.visibility import query_target
from sqlbuild.compiler.scopes.models import (
    DeclarationExplanation,
    DeclarationIdentity,
    ResourceIdentity,
    ResourceRecord,
    ScopeDiagnostic,
    ScopeLookup,
    ScopeTargetQuery,
)


def explain_scope_declaration(
    *,
    lookup: ScopeLookup,
    declaration: str | DeclarationIdentity,
    target: str | PurePath | ResourceIdentity | None = None,
    at: str | PurePath | None = None,
    directory: bool = False,
) -> tuple[DeclarationExplanation, tuple[ScopeDiagnostic, ...]]:
    """Explain a qualified declaration in an optional resource/path context."""

    context: ResourceRecord | None = None
    diagnostics: tuple[ScopeDiagnostic, ...] = ()
    if at is not None:
        _resource, context, diagnostics = _prospective_resource(
            lookup=lookup, at=at, directory=directory
        )
    elif target is not None:
        query: ScopeTargetQuery = query_target(lookup=lookup, target=target)
        context = query.matches[0] if len(query.matches) == 1 else None
    explanation, explanation_diagnostics = explain_declaration(
        lookup=lookup, target=declaration, at=context
    )
    return explanation, (*diagnostics, *explanation_diagnostics)
