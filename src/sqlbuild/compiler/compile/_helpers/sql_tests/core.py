"""SQL-native test compile-semantic extraction helpers."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.constants import (
    DEFAULT_SQL_TEST_MODE,
    EXPECTED_TEST_CTE_PREFIX,
    OMITTED_CEREMONIAL_SELECT_SQL,
    SQL_ARGUMENT_SEPARATOR_TOKEN,
    SQL_CEREMONIAL_SELECT_VALUE,
    SQL_OPEN_PAREN_TOKEN,
    SQL_QUOTE_TOKENS,
    SQL_STATEMENT_TERMINATOR_TOKEN,
    SQL_WITH_KEYWORD,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlTestCte,
    SqlReferenceOrigin,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main._find_matching_paren import find_matching_paren
from sqlbuild.compiler.sql_analysis.main._is_identifier_character import (
    is_identifier_character,
)
from sqlbuild.compiler.sql_analysis.main._is_identifier_start import is_identifier_start
from sqlbuild.compiler.sql_analysis.main._skip_dialect_non_code import dialect_non_code_end
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

_CONTEXT: str = "SQL test"
_SQL_TEST_WITH_REQUIREMENT: str = "mock CTEs and one __expected__<model> CTE"
_MATERIALIZED_KEYWORD: str = "MATERIALIZED"
_NOT_KEYWORD: str = "NOT"


def extract_unclassified_sql_test_ctes(
    *, sql: str, file_label: str, syntax: SqlLexicalSyntax
) -> tuple[CompileSqlTestCte, ...]:
    """Extract raw top-level CTEs before mode-specific classification."""

    return extract_top_level_ctes_with_scanner(
        sql=sql,
        file_label=file_label,
        context_label=_CONTEXT,
        with_requirement=_SQL_TEST_WITH_REQUIREMENT,
        cte_type=CompileSqlTestCte,
        syntax=syntax,
    )


def extract_sql_test_expected_model_names(
    *,
    sql: str,
    file_label: str,
    syntax: SqlLexicalSyntax,
    mode: SqlTestMode = DEFAULT_SQL_TEST_MODE,
) -> tuple[str, ...]:
    """Extract explicit expected-model relationships without inspecting CTE bodies."""

    if mode is not SqlTestMode.MODEL:
        return ()
    start: int = _skip_ignorable(sql=sql, start=0, syntax=syntax)
    if _try_consume_keyword(sql=sql, start=start, keyword=SQL_WITH_KEYWORD) is None:
        return ()
    ctes: tuple[CompileSqlTestCte, ...] = extract_top_level_ctes_with_scanner(
        sql=sql,
        file_label=file_label,
        context_label=_CONTEXT,
        with_requirement=_SQL_TEST_WITH_REQUIREMENT,
        cte_type=CompileSqlTestCte,
        syntax=syntax,
    )
    return tuple(
        _require_prefixed_name(
            cte_name=cte.name,
            prefix=EXPECTED_TEST_CTE_PREFIX,
            label="__expected__<model>",
            file_label=file_label,
        )
        for cte in ctes
        if cte.name.startswith(EXPECTED_TEST_CTE_PREFIX)
    )


def extract_assertion_target_model_names(
    *,
    assertion_sql: tuple[str, ...],
    syntax: SqlLexicalSyntax,
    origin: SqlReferenceOrigin | None = None,
) -> tuple[str, ...]:
    """Extract assertion model targets in authored order using canonical references."""

    targets: list[str] = []
    for sql in assertion_sql:
        targets.extend(
            reference.ref_name
            for reference in extract_sql_references(sql=sql, syntax=syntax, origin=origin)
            if reference.ref_kind == SqlReferenceKind.REF
        )
    return tuple(dict.fromkeys(targets))


@lru_cache(maxsize=4096)
def extract_top_level_ctes_with_scanner[CteT](
    *,
    sql: str,
    file_label: str,
    context_label: str,
    with_requirement: str,
    cte_type: Callable[..., CteT],
    syntax: SqlLexicalSyntax,
) -> tuple[CteT, ...]:
    """Scan top-level `WITH` CTEs, optionally followed by the ceremonial `SELECT 1`."""

    ctes: tuple[tuple[str, str], ...]
    index: int
    ctes, index = _scan_top_level_ctes(
        sql=sql,
        file_label=file_label,
        context_label=context_label,
        with_requirement=with_requirement,
        syntax=syntax,
    )
    _validate_ceremonial_select(
        sql=sql,
        start=index,
        file_label=file_label,
        context_label=context_label,
        syntax=syntax,
    )
    return tuple(cte_type(name=name, sql_body=body) for name, body in ctes)


def complete_omitted_ceremonial_select(*, sql: str, syntax: SqlLexicalSyntax) -> str:
    """Return test or scenario SQL as one statement, adding an omitted trailing `SELECT 1`."""

    offset: int | None = _native.omitted_ceremonial_select(sql, syntax.native_mapping)
    if offset is None:
        return sql
    return f"{sql[:offset]}{OMITTED_CEREMONIAL_SELECT_SQL}{sql[offset:]}"


def _scan_top_level_ctes(
    *,
    sql: str,
    file_label: str,
    context_label: str,
    with_requirement: str,
    syntax: SqlLexicalSyntax,
) -> tuple[tuple[tuple[str, str], ...], int]:
    """Return top-level CTEs and the first code position after them."""

    with_end: int | None = _try_consume_keyword(
        sql=sql,
        start=_skip_ignorable(sql=sql, start=0, context_label=context_label, syntax=syntax),
        keyword=SQL_WITH_KEYWORD,
    )
    if with_end is None:
        raise CompileInputError(
            f"{context_label} '{file_label}' must declare {with_requirement} in a top-level "
            "WITH clause"
        )
    index: int = _skip_ignorable(
        sql=sql, start=with_end, context_label=context_label, syntax=syntax
    )
    recursive_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="RECURSIVE")
    if recursive_end is not None:
        index = _skip_ignorable(
            sql=sql, start=recursive_end, context_label=context_label, syntax=syntax
        )

    ctes: list[tuple[str, str]] = []
    seen_cte_names: set[str] = set()
    while True:
        cte_name, index = _read_identifier(
            sql=sql, start=index, file_label=file_label, context_label=context_label
        )
        if cte_name in seen_cte_names:
            raise CompileInputError(
                f"{context_label} '{file_label}' defines duplicate CTE '{cte_name}'"
            )
        seen_cte_names.add(cte_name)

        index = _skip_ignorable(sql=sql, start=index, context_label=context_label, syntax=syntax)
        if index < len(sql) and sql[index] == SQL_OPEN_PAREN_TOKEN:
            index = (
                find_matching_paren(
                    sql=sql, open_paren_index=index, context=context_label, syntax=syntax
                )
                + 1
            )
            index = _skip_ignorable(
                sql=sql, start=index, context_label=context_label, syntax=syntax
            )
        index = _consume_keyword(
            sql=sql,
            start=index,
            keyword="AS",
            file_label=file_label,
            context_label=context_label,
        )
        index = _skip_ignorable(sql=sql, start=index, context_label=context_label, syntax=syntax)
        hint: str | None = _materialization_hint(
            sql=sql, start=index, context_label=context_label, syntax=syntax
        )
        if hint is not None:
            raise CompileInputError(
                f"{context_label} '{file_label}' CTE '{cte_name}' must not use AS {hint}; "
                f"materialization hints are not supported in {context_label} CTEs"
            )
        if index >= len(sql) or sql[index] != SQL_OPEN_PAREN_TOKEN:
            raise CompileInputError(
                f"{context_label} '{file_label}' CTE '{cte_name}' must use AS (...)"
            )
        cte_body_start: int = index + 1
        cte_body_end: int = find_matching_paren(
            sql=sql, open_paren_index=index, context=context_label, syntax=syntax
        )
        ctes.append((cte_name, sql[cte_body_start:cte_body_end].strip()))
        index = _skip_ignorable(
            sql=sql, start=cte_body_end + 1, context_label=context_label, syntax=syntax
        )
        if index < len(sql) and sql[index] == SQL_ARGUMENT_SEPARATOR_TOKEN:
            index = _skip_ignorable(
                sql=sql, start=index + 1, context_label=context_label, syntax=syntax
            )
            continue
        return tuple(ctes), index


def _materialization_hint(
    *, sql: str, start: int, context_label: str, syntax: SqlLexicalSyntax
) -> str | None:
    if _try_consume_keyword(sql=sql, start=start, keyword=_MATERIALIZED_KEYWORD) is not None:
        return _MATERIALIZED_KEYWORD
    not_end: int | None = _try_consume_keyword(sql=sql, start=start, keyword=_NOT_KEYWORD)
    if not_end is None:
        return None
    index: int = _skip_ignorable(sql=sql, start=not_end, context_label=context_label, syntax=syntax)
    if _try_consume_keyword(sql=sql, start=index, keyword=_MATERIALIZED_KEYWORD) is None:
        return None
    return f"{_NOT_KEYWORD} {_MATERIALIZED_KEYWORD}"


def _require_prefixed_name(
    *, cte_name: str, prefix: str, label: str, file_label: str, context_label: str = _CONTEXT
) -> str:
    extracted_name: str = cte_name.removeprefix(prefix)
    if extracted_name:
        return extracted_name
    raise CompileInputError(f"{context_label} '{file_label}' must use {label} to identify a target")


def _validate_ceremonial_select(
    *,
    sql: str,
    start: int,
    file_label: str,
    syntax: SqlLexicalSyntax,
    context_label: str = _CONTEXT,
) -> None:
    if _is_statement_end(
        sql=sql, start=start, context_label=context_label, syntax=syntax
    ) or _is_ceremonial_select_statement(
        sql=sql, start=start, context_label=context_label, syntax=syntax
    ):
        return
    raise CompileInputError(
        f"{context_label} '{file_label}' must end after its CTEs; only an optional "
        "ceremonial top-level `SELECT 1` may follow them"
    )


def _is_ceremonial_select_statement(
    *, sql: str, start: int, syntax: SqlLexicalSyntax, context_label: str = _CONTEXT
) -> bool:
    index: int = _skip_ignorable(sql=sql, start=start, context_label=context_label, syntax=syntax)
    select_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="SELECT")
    if select_end is None:
        return False
    index = _skip_ignorable(sql=sql, start=select_end, context_label=context_label, syntax=syntax)
    if index >= len(sql) or sql[index] != SQL_CEREMONIAL_SELECT_VALUE:
        return False
    index = _skip_ignorable(sql=sql, start=index + 1, context_label=context_label, syntax=syntax)
    return _is_statement_end(sql=sql, start=index, context_label=context_label, syntax=syntax)


def _is_statement_end(
    *, sql: str, start: int, syntax: SqlLexicalSyntax, context_label: str = _CONTEXT
) -> bool:
    index: int = start
    if index < len(sql) and sql[index] == SQL_STATEMENT_TERMINATOR_TOKEN:
        index = _skip_ignorable(
            sql=sql, start=index + 1, context_label=context_label, syntax=syntax
        )
    return index == len(sql)


def _consume_keyword(
    *, sql: str, start: int, keyword: str, file_label: str, context_label: str = _CONTEXT
) -> int:
    keyword_end: int | None = _try_consume_keyword(sql=sql, start=start, keyword=keyword)
    if keyword_end is not None:
        return keyword_end
    raise CompileInputError(f"{context_label} '{file_label}' expected keyword {keyword}")


def _try_consume_keyword(*, sql: str, start: int, keyword: str) -> int | None:
    keyword_end: int = start + len(keyword)
    if sql[start:keyword_end].upper() != keyword:
        return None
    if keyword_end < len(sql) and is_identifier_character(sql[keyword_end]):
        return None
    if start > 0 and is_identifier_character(sql[start - 1]):
        return None
    return keyword_end


def _read_identifier(
    *, sql: str, start: int, file_label: str, context_label: str = _CONTEXT
) -> tuple[str, int]:
    if start >= len(sql) or not is_identifier_start(sql[start]):
        raise CompileInputError(f"{context_label} '{file_label}' expected a CTE name")
    index: int = start + 1
    while index < len(sql) and is_identifier_character(sql[index]):
        index += 1
    return sql[start:index], index


def _skip_ignorable(
    *, sql: str, start: int, syntax: SqlLexicalSyntax, context_label: str = _CONTEXT
) -> int:
    index: int = start
    while index < len(sql):
        if sql[index].isspace():
            index += 1
            continue
        if sql[index] not in SQL_QUOTE_TOKENS:
            comment_end: int | None = dialect_non_code_end(
                sql=sql, start=index, syntax=syntax, context=context_label
            )
            if comment_end is not None:
                index = comment_end
                continue
        return index
    return index
