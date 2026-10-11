"""Validation helpers for executable SQL resolution."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.references.types import SqlReferenceKind

_MARKER_KINDS: tuple[tuple[SqlReferenceKind, str], ...] = (
    (SqlReferenceKind.REF, "R001"),
    (SqlReferenceKind.SEED, "R002"),
    (SqlReferenceKind.SOURCE, "R003"),
    (SqlReferenceKind.UDF, "R004"),
    (SqlReferenceKind.TABLE_FUNCTION, "R005"),
)


def assert_no_unresolved_sql_markers(*, sql: str, context: str) -> None:
    """Fail fast if executable SQL still contains unresolved ref/source markers."""

    marker, unclosed = _native.unresolved_reference_marker_kind(sql, context)
    if unclosed is not None:
        raise CompileInputError(unclosed)
    if marker is None:
        return
    kind, code = _MARKER_KINDS[marker]
    raise _coded_value_error(
        message=f"{context} still contains unresolved {kind.placeholder_call()} markers",
        code=code,
    )


def _coded_value_error(*, message: str, code: str) -> ValueError:
    error: ValueError = ValueError(message)
    object.__setattr__(error, "message", message)
    object.__setattr__(error, "code", code)
    return error
