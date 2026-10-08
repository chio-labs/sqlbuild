"""Scan `@enum`/`@const` references of many SQL strings in one native call."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.model_loop.types import NativeDeclarationScan


def scan_native_declaration_references(
    *, sqls: tuple[str, ...]
) -> tuple[NativeDeclarationScan | None, ...]:
    """Return each string's references and the code of the error ending its walk, or None."""

    return tuple(
        None if scan is None else (tuple(scan[0]), scan[1])
        for scan in _native.scan_sql_declaration_references(list(sqls))
    )
