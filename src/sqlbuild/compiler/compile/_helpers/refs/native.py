"""Logical SQL references extracted by the native scanner."""

from __future__ import annotations

from functools import cache

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def extract_native_sql_references(
    *, sql: str, syntax: SqlLexicalSyntax
) -> tuple[CompileSqlReference, ...] | str | None:
    """Return the references, the message Python raises, or None where Python must extract."""

    try:
        extraction: (
            tuple[list[tuple[str, str, str | None, int | None]], None] | tuple[None, str] | None
        ) = _scanner(syntax).extract(sql)
    except UnicodeError:
        return None
    if extraction is None:
        return None
    references, message = extraction
    if references is None:
        return message
    return tuple(
        CompileSqlReference(
            ref_kind=SqlReferenceKind(kind),
            ref_name=name,
            ref_package=package,
            call_argument_count=call_argument_count,
        )
        for kind, name, package, call_argument_count in references
    )


@cache
def _scanner(syntax: SqlLexicalSyntax) -> _native.SqlReferenceScanner:
    return _native.SqlReferenceScanner(syntax.native_mapping)
