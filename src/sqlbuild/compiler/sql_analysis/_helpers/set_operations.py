"""Top-level SQL set-operation scanning over the shared code-position iterator."""

from __future__ import annotations

from sqlbuild.compiler.sql_analysis._helpers.scanning import (
    is_identifier_character_impl,
    iter_code_positions_impl,
    skip_block_comment_impl,
    skip_line_comment_impl,
)

_SET_OPERATOR_KEYWORDS: tuple[str, ...] = ("UNION", "INTERSECT")
_EXCEPT_KEYWORD: str = "EXCEPT"
_ALL_KEYWORD: str = "ALL"
_DISTINCT_KEYWORD: str = "DISTINCT"
_STAR_CHARACTER: str = "*"


def split_set_operation_branches_impl(*, sql: str, context: str) -> tuple[str, ...]:
    """Split SQL on top-level `UNION`, `INTERSECT` and `EXCEPT` with optional quantifiers."""

    branches: list[str] = []
    branch_start: int = 0
    resume: int = 0
    previous_code: str | None = None
    previous_depth: int = 0
    index: int
    depth: int
    for index, depth in iter_code_positions_impl(sql=sql, context=context):
        if depth != previous_depth:
            previous_code = None
        previous_depth = depth
        operator_end: int | None = (
            None
            if index < resume or depth != 0
            else _set_operator_end(sql=sql, start=index, previous_code=previous_code)
        )
        if not sql[index].isspace():
            previous_code = sql[index]
        if operator_end is None:
            continue
        branch_sql: str = sql[branch_start:index].strip()
        if branch_sql:
            branches.append(branch_sql)
        resume = _skip_ignorable(sql=sql, start=operator_end, context=context)
        quantifier_end: int | None = _keyword_end(
            sql=sql, start=resume, keyword=_ALL_KEYWORD
        ) or _keyword_end(sql=sql, start=resume, keyword=_DISTINCT_KEYWORD)
        if quantifier_end is not None:
            resume = _skip_ignorable(sql=sql, start=quantifier_end, context=context)
        branch_start = resume
    final_branch_sql: str = sql[branch_start:].strip()
    if final_branch_sql:
        branches.append(final_branch_sql)
    return tuple(branches)


def _set_operator_end(*, sql: str, start: int, previous_code: str | None) -> int | None:
    """Return a set operator's end; `* EXCEPT (...)` star modifiers are not operators."""

    keyword: str
    for keyword in _SET_OPERATOR_KEYWORDS:
        keyword_end: int | None = _keyword_end(sql=sql, start=start, keyword=keyword)
        if keyword_end is not None:
            return keyword_end
    if previous_code == _STAR_CHARACTER:
        return None
    return _keyword_end(sql=sql, start=start, keyword=_EXCEPT_KEYWORD)


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
