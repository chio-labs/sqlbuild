"""Visibility of one declaration from an authored consumer path."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.visibility import (
    declaration_lexical_path,
    path_visibility_reason,
)
from sqlbuild.compiler.scopes.models import DeclarationRecord
from sqlbuild.compiler.scopes.types import VisibilityReason


def declaration_visibility(
    *, declaration: DeclarationRecord, consumer: str | PurePath | DeclarationRecord
) -> VisibilityReason | None:
    """Return why a declaration is visible from a resource path or a declaration's owner folder."""

    path: str | PurePath = (
        declaration_lexical_path(record=consumer)
        if isinstance(consumer, DeclarationRecord)
        else consumer
    )
    return path_visibility_reason(declaration=declaration, path=path)
