"""Dialect-aware SQL quoted text and comment scanning entrypoint."""

from sqlbuild.compiler.sql_analysis._helpers.scanning import dialect_non_code_end_impl
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def dialect_non_code_end(
    *, sql: str, start: int, syntax: SqlLexicalSyntax, context: str = "SQL"
) -> int | None:
    """Return the end of the quoted text or comment at the position under the dialect's rules."""

    return dialect_non_code_end_impl(sql=sql, start=start, syntax=syntax, context=context)
