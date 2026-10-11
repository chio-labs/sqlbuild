"""Scan `@enum`/`@const` references of many SQL strings in one native call."""

from __future__ import annotations

import sys
import unicodedata
from collections.abc import Callable

import sqlbuild._native as _native
from sqlbuild.compiler.model_loop.types import NativeDeclarationScan


def scan_native_declaration_references(
    *, sqls: tuple[str, ...], skip_malformed: bool = False
) -> tuple[NativeDeclarationScan, ...]:
    """Return each string's references and stop code; `skip_malformed` walks past malformed ones."""

    scan_references: Callable[
        [list[str], tuple[int, int], str],
        list[tuple[list[tuple[int, str, str | None, int, int]], int | None]],
    ] = (
        _native.scan_sql_declaration_usages
        if skip_malformed
        else _native.scan_sql_declaration_references
    )
    return tuple(
        (tuple(scan[0]), scan[1])
        for scan in scan_references(
            list(sqls), (sys.version_info[0], sys.version_info[1]), unicodedata.unidata_version
        )
    )
