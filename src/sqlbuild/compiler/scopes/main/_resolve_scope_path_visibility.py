"""Resolve declaration visibility for any authored project-relative path."""

from __future__ import annotations

from pathlib import PurePath

import sqlbuild._native as _native
from sqlbuild.compiler.scopes.models import DeclarationRecord, ScopeLookup


def resolve_scope_path_visibility(
    *, lookup: ScopeLookup, path: str | PurePath
) -> tuple[tuple[DeclarationRecord, ...], tuple[DeclarationRecord, ...]]:
    """Return visible and inaccessible declarations for an authored path."""

    return _native.scope_resolve_path_visibility(lookup, path)
