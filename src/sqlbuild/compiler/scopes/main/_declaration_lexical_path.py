"""Lexical location of a declaration file for visibility resolution."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers import visibility
from sqlbuild.compiler.scopes.models import DeclarationRecord


def declaration_lexical_path(*, record: DeclarationRecord) -> str:
    """Return the authored path whose folder controls what a declaration file can use."""

    return visibility.declaration_lexical_path(record=record)
