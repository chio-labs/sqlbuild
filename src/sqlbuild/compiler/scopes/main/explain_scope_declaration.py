"""Public detailed declaration explanation operation."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.reports import explain_declaration
from sqlbuild.compiler.scopes.models import (
    DeclarationExplanation,
    DeclarationIdentity,
    ResourceIdentity,
    ScopeDiagnostic,
    ScopeLookup,
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

    return explain_declaration(
        lookup=lookup, declaration=declaration, target=target, at=at, directory=directory
    )
