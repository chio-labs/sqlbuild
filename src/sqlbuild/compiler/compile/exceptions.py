"""Expected exceptions for the pre-semantic compile attachment layer."""

from __future__ import annotations

from sqlbuild._native import CompileInputError


class MacroDeclarationLookupError(CompileInputError, KeyError):
    """Retain authored diagnostics while honoring the Mapping lookup contract."""
