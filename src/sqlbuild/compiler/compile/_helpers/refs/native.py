"""Logical SQL references extracted by the native scanner."""

from __future__ import annotations

from functools import cache
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    CompileSqlReference,
    InvalidSqlReferenceCall,
    SqlReferenceScan,
)
from sqlbuild.compiler.compile.types import SqlReferenceScanFailure
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

type _NativeExtraction = (
    tuple[
        tuple[
            list[tuple[str, str, str | None, int | None]],
            list[tuple[str, str, int, str, str, str]],
        ],
        None,
    ]
    | tuple[None, tuple[str, int]]
)


def extract_native_sql_references(
    *, sql: str, syntax: SqlLexicalSyntax
) -> SqlReferenceScan | SqlReferenceScanFailure:
    """Return the references and rejected calls, or the scan error and its start."""

    extraction: _NativeExtraction = _scanner(syntax).extract(sql)
    scanned, failure = extraction
    if scanned is None:
        return cast(SqlReferenceScanFailure, failure)
    references, invalid_calls = scanned
    return SqlReferenceScan(
        references=tuple(
            CompileSqlReference(
                ref_kind=SqlReferenceKind(kind),
                ref_name=name,
                ref_package=package,
                call_argument_count=call_argument_count,
            )
            for kind, name, package, call_argument_count in references
        ),
        invalid_calls=tuple(
            InvalidSqlReferenceCall(
                ref_kind=SqlReferenceKind(kind),
                call=call,
                start=start,
                message=call_message,
                help=help_text,
                corrected_call=corrected_call,
            )
            for kind, call, start, call_message, help_text, corrected_call in invalid_calls
        ),
    )


@cache
def _scanner(syntax: SqlLexicalSyntax) -> _native.SqlReferenceScanner:
    return _native.SqlReferenceScanner(syntax.native_mapping)
