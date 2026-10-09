"""Scan `@enum`/`@const` references of many SQL strings in one native call."""

from __future__ import annotations

import sys
import unicodedata

import sqlbuild._native as _native
from sqlbuild.compiler.model_loop.types import NativeDeclarationScan


def scan_native_declaration_references(
    *, sqls: tuple[str, ...]
) -> tuple[NativeDeclarationScan, ...]:
    """Return each string's references and the code of the error ending its walk."""

    return tuple(
        (tuple(scan[0]), scan[1])
        for scan in _native.scan_sql_declaration_references(
            list(sqls), (sys.version_info[0], sys.version_info[1]), unicodedata.unidata_version
        )
    )
