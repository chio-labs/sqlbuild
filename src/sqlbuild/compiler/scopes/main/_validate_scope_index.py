"""Strict validation for an already-built, fact-preserving scope index."""

from __future__ import annotations

from sqlbuild.compiler.scopes.exceptions import ScopeValidationError
from sqlbuild.compiler.scopes.models import ScopeDiagnostic, ScopeIndex
from sqlbuild.compiler.scopes.types import DiagnosticSeverity


def validate_scope_index(*, index: ScopeIndex) -> None:
    """Raise one aggregate compiler error when the index has error diagnostics."""

    errors: tuple[ScopeDiagnostic, ...] = tuple(
        item for item in index.diagnostics if item.severity is DiagnosticSeverity.ERROR
    )
    if errors:
        raise ScopeValidationError(errors)
