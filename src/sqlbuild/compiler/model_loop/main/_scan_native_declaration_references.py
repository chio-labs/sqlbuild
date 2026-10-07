"""Scan `@enum`/`@const` references of many SQL strings in one native call."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.model_loop.types import NativeDeclarationReference


def scan_native_declaration_references(
    *, sqls: tuple[str, ...]
) -> tuple[tuple[NativeDeclarationReference, ...] | None, ...]:
    """Return each string's `(kind code, name, member, start, end)` references, or None."""

    return tuple(
        None if references is None else tuple(references)
        for references in _native.scan_sql_declaration_references(list(sqls))
    )
