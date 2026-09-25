"""Top-level SQL set-operation scanning over the shared code-position iterator."""

from __future__ import annotations

from sqlbuild.compiler.sql_analysis._helpers.scanning import (
    is_identifier_character_impl,
    iter_code_positions_impl,
    skip_block_comment_impl,
    skip_line_comment_impl,
)

_UNION_KEYWORD: str = "UNION"
_UNION_ALL_KEYWORD: str = "ALL"
_UNION_DISTINCT_KEYWORD: str = "DISTINCT"


def split_union_branches_impl(*, sql: str, context: str) -> tuple[str, ...]:
    """Split SQL on top-level `UNION [ALL | DISTINCT]`, ignoring quotes and comments."""

    branches: list[str] = []
    branch_start: int = 0
    resume: int = 0
    index: int
    depth: int
    for index, depth in iter_code_positions_impl(sql=sql, context=context):
        if index < resume or depth != 0:
            continue
        union_end: int | None = _keyword_end(sql=sql, start=index, keyword=_UNION_KEYWORD)
        if union_end is None:
            continue
        branch_sql: str = sql[branch_start:index].strip()
        if branch_sql:
            branches.append(branch_sql)
        resume = _skip_ignorable(sql=sql, start=union_end, context=context)
        quantifier_end: int | None = _keyword_end(
            sql=sql, start=resume, keyword=_UNION_ALL_KEYWORD
        ) or _keyword_end(sql=sql, start=resume, keyword=_UNION_DISTINCT_KEYWORD)
        if quantifier_end is not None:
            resume = _skip_ignorable(sql=sql, start=quantifier_end, context=context)
        branch_start = resume
    final_branch_sql: str = sql[branch_start:].strip()
    if final_branch_sql:
        branches.append(final_branch_sql)
    return tuple(branches)


def contains_top_level_keyword_impl(*, sql: str, keywords: tuple[str, ...], context: str) -> bool:
    """Return whether any keyword appears as top-level code outside quotes and comments."""

    index: int
    depth: int
    for index, depth in iter_code_positions_impl(sql=sql, context=context):
        if depth != 0:
            continue
        keyword: str
        for keyword in keywords:
            if _keyword_end(sql=sql, start=index, keyword=keyword) is not None:
                return True
    return False


def _keyword_end(*, sql: str, start: int, keyword: str) -> int | None:
    keyword_end: int = start + len(keyword)
    if sql[start:keyword_end].upper() != keyword:
        return None
    if keyword_end < len(sql) and is_identifier_character_impl(sql[keyword_end]):
        return None
    if start > 0 and is_identifier_character_impl(sql[start - 1]):
        return None
    return keyword_end


def _skip_ignorable(*, sql: str, start: int, context: str) -> int:
    index: int = start
    while index < len(sql):
        if sql[index].isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            index = skip_line_comment_impl(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment_impl(sql=sql, start=index, context=context)
            continue
        return index
    return index
