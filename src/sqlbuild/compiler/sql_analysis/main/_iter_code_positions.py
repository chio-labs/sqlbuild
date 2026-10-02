"""Top-level SQL code position scanning entrypoint."""

from collections.abc import Iterator

from sqlbuild.compiler.sql_analysis._helpers.scanning import iter_code_positions_impl
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def iter_code_positions(
    *, sql: str, context: str = "SQL", syntax: SqlLexicalSyntax | None = None
) -> Iterator[tuple[int, int]]:
    """Yield each code offset outside comments and quotes with its parenthesis depth."""

    return iter_code_positions_impl(sql=sql, context=context, syntax=syntax)
