"""Top-level SQL keyword detection entrypoint."""

from sqlbuild.compiler.sql_analysis._helpers.set_operations import (
    contains_top_level_keyword_impl,
)


def contains_top_level_keyword(
    *, sql: str, keywords: tuple[str, ...], context: str = "SQL"
) -> bool:
    """Return whether any keyword appears as top-level code outside quotes and comments."""

    return contains_top_level_keyword_impl(sql=sql, keywords=keywords, context=context)
