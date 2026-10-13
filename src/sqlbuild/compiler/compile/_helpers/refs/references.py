"""Logical SQL reference extraction helpers for compile semantics."""

from __future__ import annotations

from functools import cache
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile.constants import REFERENCE_CALL_SYNTAX_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
    CompileSqlReference,
    InvalidSqlReferenceCall,
    SqlReferenceScan,
)
from sqlbuild.compiler.compile.types import (
    DiagnosticPhase,
    DiagnosticSeverity,
    SqlReferenceScanFailure,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def extract_sql_references(
    *, sql: str, syntax: SqlLexicalSyntax
) -> tuple[CompileSqlReference, ...]:
    """Return logical SQL refs outside comments and quotes, reporting rejected calls as P012."""

    scan: SqlReferenceScan = scan_sql_reference_calls(sql=sql, syntax=syntax)
    for invalid_call in scan.invalid_calls:
        report_compile_diagnostic(
            key=(REFERENCE_CALL_SYNTAX_CODE, "", invalid_call.call),
            diagnostic=CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity.ERROR,
                code=REFERENCE_CALL_SYNTAX_CODE,
                message=invalid_call.message,
                help=invalid_call.help,
            ),
        )
    return scan.references


def scan_sql_reference_calls(*, sql: str, syntax: SqlLexicalSyntax) -> SqlReferenceScan:
    """Return valid references and rejected calls; a scan error raises unlocated."""

    scanned, failure = _scanner(syntax).extract(sql)
    if scanned is None:
        raise CompileInputError(cast(SqlReferenceScanFailure, failure)[0])
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
