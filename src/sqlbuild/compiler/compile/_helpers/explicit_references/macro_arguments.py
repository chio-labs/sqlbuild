"""Typed reference arguments and explicit-reference enforcement for macro expansion."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.refs.references import (
    extract_sql_references,
)
from sqlbuild.compiler.compile.models import (
    CompileSqlReference,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind

_TYPED_REFERENCE_KINDS: dict[str, SqlResourceRefKind] = {
    "__ref": SqlResourceRefKind.MODEL,
    "__source": SqlResourceRefKind.SOURCE,
    "__seed": SqlResourceRefKind.SEED,
}
_REFERENCE_FUNCTION_BY_KIND: dict[SqlResourceRefKind, str] = {
    kind: function for function, kind in _TYPED_REFERENCE_KINDS.items()
}

_GENERIC_SQL_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax()


def reference_call_text(ref: SqlResourceRef) -> str:
    """Return the SQL reference call that names ``ref``, such as ``__ref("orders")``."""

    return f'{_REFERENCE_FUNCTION_BY_KIND[ref.kind]}("{ref.name}")'


def call_site_sql_references(
    refs: tuple[SqlResourceRef, ...],
) -> tuple[CompileSqlReference, ...]:
    """Return the SQL references written as typed macro arguments, as SQL extraction sees them."""

    if not refs:
        return ()
    return extract_sql_references(
        sql=" ".join(reference_call_text(ref) for ref in refs), syntax=_GENERIC_SQL_SYNTAX
    )


def merge_call_site_references(
    *,
    references: tuple[CompileSqlReference, ...],
    argument_references: tuple[CompileSqlReference, ...],
) -> tuple[CompileSqlReference, ...]:
    """Add typed macro arguments to the references found in expanded SQL, once each."""

    if not argument_references:
        return references
    return tuple(dict.fromkeys((*references, *argument_references)))


def typed_reference_kinds() -> dict[str, SqlResourceRefKind]:
    """Each typed reference function, such as `__ref`, and the resource kind it names."""

    return dict(_TYPED_REFERENCE_KINDS)
