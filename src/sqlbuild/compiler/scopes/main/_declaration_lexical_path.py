"""Lexical location of a declaration file for visibility resolution."""

from __future__ import annotations

from sqlbuild.compiler.scopes.constants import (
    CURRENT_PATH_COMPONENT,
    DECLARATION_LEXICAL_STEM,
    PATH_SEPARATOR,
)
from sqlbuild.compiler.scopes.models import DeclarationRecord


def declaration_lexical_path(*, record: DeclarationRecord) -> str:
    """Return the authored path whose folder controls what a declaration file can use."""

    return (
        f"{record.owning_path or CURRENT_PATH_COMPONENT}{PATH_SEPARATOR}{DECLARATION_LEXICAL_STEM}"
    )
