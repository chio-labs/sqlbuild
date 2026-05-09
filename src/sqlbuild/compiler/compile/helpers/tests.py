"""SQL-native test compile-semantic extraction helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import (
    ASSERT_TEST_CTE_PREFIX,
    EXPECTED_TEST_CTE_PREFIX,
    MACRO_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    RESERVED_SQL_TEST_CTE_NAMES,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.sql_scanning import (
    find_matching_paren,
    is_identifier_character,
    is_identifier_start,
    skip_block_comment,
    skip_line_comment,
    skip_quoted_text,
)
from sqlbuild.compiler.compile.helpers.sqlglot_tests import (
    extract_expected_branch_column_names_with_sqlglot,
)
from sqlbuild.compiler.compile.models import CompileSqlTestCte, CompileSqlTestCtes

_CONTEXT: str = "SQL test"


def extract_sql_test_ctes(*, sql: str, file_label: str) -> CompileSqlTestCtes:
    """Extract top-level SQL-native test mock and expected CTEs."""

    index: int = _skip_ignorable(sql=sql, start=0)
    index = _consume_keyword(sql=sql, start=index, keyword="WITH", file_label=file_label)
    index = _skip_ignorable(sql=sql, start=index)
    recursive_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="RECURSIVE")
    if recursive_end is not None:
        index = _skip_ignorable(sql=sql, start=recursive_end)

    ctes: list[CompileSqlTestCte] = []
    seen_cte_names: set[str] = set()
    while True:
        cte_name, index = _read_identifier(sql=sql, start=index, file_label=file_label)
        if cte_name in seen_cte_names:
            raise CompileInputError(f"SQL test '{file_label}' defines duplicate CTE '{cte_name}'")
        seen_cte_names.add(cte_name)

        index = _skip_ignorable(sql=sql, start=index)
        if index < len(sql) and sql[index] == "(":
            index = find_matching_paren(sql=sql, open_paren_index=index, context=_CONTEXT) + 1
            index = _skip_ignorable(sql=sql, start=index)
        index = _consume_keyword(sql=sql, start=index, keyword="AS", file_label=file_label)
        index = _skip_ignorable(sql=sql, start=index)
        if index >= len(sql) or sql[index] != "(":
            raise CompileInputError(f"SQL test '{file_label}' CTE '{cte_name}' must use AS (...)")
        cte_body_start: int = index + 1
        cte_body_end: int = find_matching_paren(sql=sql, open_paren_index=index, context=_CONTEXT)
        ctes.append(
            CompileSqlTestCte(
                name=cte_name,
                sql_body=sql[cte_body_start:cte_body_end].strip(),
            )
        )
        index = _skip_ignorable(sql=sql, start=cte_body_end + 1)
        if index < len(sql) and sql[index] == ",":
            index = _skip_ignorable(sql=sql, start=index + 1)
            continue
        break

    _validate_ceremonial_select(sql=sql, start=index, file_label=file_label)
    return _classify_sql_test_ctes(ctes=tuple(ctes), file_label=file_label)


def _classify_sql_test_ctes(
    *, ctes: tuple[CompileSqlTestCte, ...], file_label: str
) -> CompileSqlTestCtes:
    authored_ctes: list[CompileSqlTestCte] = []
    macro_mocks: dict[str, str] = {}
    mock_model_names: list[str] = []
    mock_source_names: list[str] = []
    mock_seed_names: list[str] = []
    expected_model_names: list[str] = []
    assertion_ctes: list[CompileSqlTestCte] = []
    assertion_names: list[str] = []

    cte: CompileSqlTestCte
    for cte in ctes:
        if cte.name.startswith(MACRO_TEST_CTE_PREFIX):
            macro_name: str = _require_prefixed_name(
                cte_name=cte.name,
                prefix=MACRO_TEST_CTE_PREFIX,
                label="__macro__<macro>",
                file_label=file_label,
            )
            macro_mocks[macro_name] = _extract_macro_mock_value(cte=cte, file_label=file_label)
            continue
        if cte.name.startswith(REF_TEST_CTE_PREFIX):
            mock_model_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=REF_TEST_CTE_PREFIX,
                    label="__ref__<model>",
                    file_label=file_label,
                )
            )
            authored_ctes.append(cte)
            continue
        if cte.name.startswith(SOURCE_TEST_CTE_PREFIX):
            mock_source_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=SOURCE_TEST_CTE_PREFIX,
                    label="__source__<source>",
                    file_label=file_label,
                )
            )
            authored_ctes.append(cte)
            continue
        if cte.name.startswith(SEED_TEST_CTE_PREFIX):
            mock_seed_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=SEED_TEST_CTE_PREFIX,
                    label="__seed__<seed>",
                    file_label=file_label,
                )
            )
            authored_ctes.append(cte)
            continue
        if cte.name.startswith(EXPECTED_TEST_CTE_PREFIX):
            expected_model_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=EXPECTED_TEST_CTE_PREFIX,
                    label="__expected__<model>",
                    file_label=file_label,
                )
            )
            _validate_expected_cte_query(cte=cte, file_label=file_label)
            continue
        if cte.name.startswith(ASSERT_TEST_CTE_PREFIX):
            assertion_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=ASSERT_TEST_CTE_PREFIX,
                    label="__assert__<assertion>",
                    file_label=file_label,
                )
            )
            assertion_ctes.append(cte)
            continue
        if cte.name in RESERVED_SQL_TEST_CTE_NAMES:
            raise CompileInputError(
                f"SQL test '{file_label}' uses reserved helper CTE name '{cte.name}'"
            )
        authored_ctes.append(cte)

    if not mock_model_names and not mock_source_names and not mock_seed_names:
        raise CompileInputError(
            f"SQL test '{file_label}' must define at least one __ref__*, __source__*, "
            "or __seed__* mock CTE"
        )
    if not expected_model_names and not assertion_names:
        raise CompileInputError(
            f"SQL test '{file_label}' must define at least one __expected__<model> or "
            "__assert__<assertion> CTE"
        )
    return CompileSqlTestCtes(
        authored_ctes=tuple(authored_ctes),
        macro_mocks=macro_mocks,
        mock_model_names=tuple(mock_model_names),
        mock_source_names=tuple(mock_source_names),
        mock_seed_names=tuple(mock_seed_names),
        expected_model_names=tuple(expected_model_names),
        assertion_ctes=tuple(assertion_ctes),
        assertion_names=tuple(assertion_names),
    )


def _extract_macro_mock_value(*, cte: CompileSqlTestCte, file_label: str) -> str:
    """Extract the single SQL string literal value from a __macro__ CTE."""

    body: str = cte.sql_body.strip()
    index: int = _skip_ignorable(sql=body, start=0)
    index = _consume_keyword(sql=body, start=index, keyword="SELECT", file_label=file_label)
    index = _skip_ignorable(sql=body, start=index)
    if index >= len(body) or body[index] != "'":
        raise CompileInputError(
            f"SQL test '{file_label}' macro mock '{cte.name}' must be a single SELECT string "
            "literal, for example SELECT '''US'''"
        )
    value: str
    value, index = _read_sql_string_literal(sql=body, start=index)
    index = _skip_ignorable(sql=body, start=index)
    if index < len(body) and body[index] == ";":
        index = _skip_ignorable(sql=body, start=index + 1)
    if index != len(body):
        raise CompileInputError(
            f"SQL test '{file_label}' macro mock '{cte.name}' must be a single SELECT string "
            "literal with no FROM, UNION, or additional columns"
        )
    return value


def _read_sql_string_literal(*, sql: str, start: int) -> tuple[str, int]:
    """Read one single-quoted SQL string literal and unescape doubled quotes."""

    value_parts: list[str] = []
    index: int = start + 1
    while index < len(sql):
        char: str = sql[index]
        if char == "'":
            if index + 1 < len(sql) and sql[index + 1] == "'":
                value_parts.append("'")
                index += 2
                continue
            return "".join(value_parts), index + 1
        value_parts.append(char)
        index += 1
    raise CompileInputError("SQL test macro mock has an unterminated string literal")


def _validate_expected_cte_query(*, cte: CompileSqlTestCte, file_label: str) -> None:
    if _contains_select_star(cte.sql_body):
        raise CompileInputError(
            f"SQL test '{file_label}' must not use SELECT * in __expected__<model> CTEs"
        )
    branch_column_names: tuple[tuple[str, ...], ...] = _extract_expected_branch_column_names(
        sql=cte.sql_body,
        file_label=file_label,
    )
    first_branch_column_names: tuple[str, ...] = branch_column_names[0]
    branch_index: int
    for branch_index, column_names in enumerate(branch_column_names[1:], start=2):
        if column_names != first_branch_column_names:
            raise CompileInputError(
                f"SQL test '{file_label}' must use the same __expected__<model> "
                f"projection names and order in every set-operation branch; branch {branch_index} "
                "does not match branch 1"
            )


def _extract_expected_branch_column_names(
    *, sql: str, file_label: str
) -> tuple[tuple[str, ...], ...]:
    sqlglot_column_names: tuple[tuple[str, ...], ...] | None = (
        extract_expected_branch_column_names_with_sqlglot(sql=sql, file_label=file_label)
    )
    if sqlglot_column_names is not None:
        return sqlglot_column_names
    branches: tuple[str, ...] = _split_set_operation_branches(sql)
    return tuple(
        _extract_expected_select_column_names(branch_sql=branch, file_label=file_label)
        for branch in branches
    )


def _split_set_operation_branches(sql: str) -> tuple[str, ...]:
    branches: list[str] = []
    branch_start: int = 0
    index: int = 0
    depth: int = 0
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql[index] in {"'", '"', "`"}:
            index = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql[index] == "(":
            depth += 1
            index += 1
            continue
        if sql[index] == ")":
            depth -= 1
            index += 1
            continue
        union_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="UNION")
        if depth == 0 and union_end is not None:
            branch_sql: str = sql[branch_start:index].strip()
            if branch_sql:
                branches.append(branch_sql)
            index = _skip_ignorable(sql=sql, start=union_end)
            all_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="ALL")
            if all_end is not None:
                index = _skip_ignorable(sql=sql, start=all_end)
            branch_start = index
            continue
        index += 1

    final_branch_sql: str = sql[branch_start:].strip()
    if final_branch_sql:
        branches.append(final_branch_sql)
    return tuple(branches)


def _extract_expected_select_column_names(*, branch_sql: str, file_label: str) -> tuple[str, ...]:
    index: int = _skip_ignorable(sql=branch_sql, start=0)
    select_end: int | None = _try_consume_keyword(sql=branch_sql, start=index, keyword="SELECT")
    if select_end is None:
        raise CompileInputError(
            f"SQL test '{file_label}' must define each __expected__<model> set-operation "
            "branch as a SELECT query"
        )
    select_list_end: int = _find_select_list_end(sql=branch_sql, start=select_end)
    raw_select_list: str = branch_sql[select_end:select_list_end]
    expressions: tuple[str, ...] = _split_top_level_commas(raw_select_list)
    if not expressions:
        raise CompileInputError(
            f"SQL test '{file_label}' must project at least one column in __expected__<model>"
        )
    return tuple(
        _extract_expected_projection_name(expression=expression, file_label=file_label)
        for expression in expressions
    )


def _find_select_list_end(*, sql: str, start: int) -> int:
    index: int = start
    depth: int = 0
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql[index] in {"'", '"', "`"}:
            index = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql[index] == "(":
            depth += 1
            index += 1
            continue
        if sql[index] == ")":
            depth -= 1
            index += 1
            continue
        if depth == 0 and _try_consume_keyword(sql=sql, start=index, keyword="FROM") is not None:
            return index
        index += 1
    return len(sql)


def _split_top_level_commas(raw_value: str) -> tuple[str, ...]:
    values: list[str] = []
    value_start: int = 0
    index: int = 0
    depth: int = 0
    while index < len(raw_value):
        if raw_value.startswith("--", index):
            index = skip_line_comment(sql=raw_value, start=index)
            continue
        if raw_value.startswith("/*", index):
            index = skip_block_comment(sql=raw_value, start=index, context=_CONTEXT)
            continue
        if raw_value[index] in {"'", '"', "`"}:
            index = skip_quoted_text(sql=raw_value, start=index, context=_CONTEXT)
            continue
        if raw_value[index] == "(":
            depth += 1
        elif raw_value[index] == ")":
            depth -= 1
        elif raw_value[index] == "," and depth == 0:
            item: str = raw_value[value_start:index].strip()
            if item:
                values.append(item)
            value_start = index + 1
        index += 1

    final_item: str = raw_value[value_start:].strip()
    if final_item:
        values.append(final_item)
    return tuple(values)


def _extract_expected_projection_name(*, expression: str, file_label: str) -> str:
    alias_name: str | None = _extract_as_alias(expression)
    if alias_name is not None:
        return alias_name
    stripped_expression: str = expression.strip()
    if _is_simple_identifier(stripped_expression):
        return stripped_expression
    raise CompileInputError(
        f"SQL test '{file_label}' must alias every non-trivial __expected__<model> projection"
    )


def _extract_as_alias(expression: str) -> str | None:
    index: int = 0
    depth: int = 0
    last_alias_name: str | None = None
    while index < len(expression):
        if expression.startswith("--", index):
            index = skip_line_comment(sql=expression, start=index)
            continue
        if expression.startswith("/*", index):
            index = skip_block_comment(sql=expression, start=index, context=_CONTEXT)
            continue
        if expression[index] in {"'", '"', "`"}:
            index = skip_quoted_text(sql=expression, start=index, context=_CONTEXT)
            continue
        if expression[index] == "(":
            depth += 1
            index += 1
            continue
        if expression[index] == ")":
            depth -= 1
            index += 1
            continue
        as_end: int | None = _try_consume_keyword(sql=expression, start=index, keyword="AS")
        if depth == 0 and as_end is not None:
            alias_index: int = _skip_ignorable(sql=expression, start=as_end)
            if alias_index < len(expression) and is_identifier_start(expression[alias_index]):
                alias_name, alias_end = _read_identifier(
                    sql=expression,
                    start=alias_index,
                    file_label="projection",
                )
                if not expression[alias_end:].strip():
                    last_alias_name = alias_name
            index = as_end
            continue
        index += 1
    return last_alias_name


def _is_simple_identifier(value: str) -> bool:
    if not value or not is_identifier_start(value[0]):
        return False
    return all(is_identifier_character(character) for character in value[1:])


def _contains_select_star(sql: str) -> bool:
    index: int = 0
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql[index] in {"'", '"', "`"}:
            index = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            continue
        select_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="SELECT")
        if select_end is not None:
            value_index: int = _skip_ignorable(sql=sql, start=select_end)
            if value_index < len(sql) and sql[value_index] == "*":
                return True
            index = select_end
            continue
        index += 1
    return False


def _require_prefixed_name(*, cte_name: str, prefix: str, label: str, file_label: str) -> str:
    extracted_name: str = cte_name.removeprefix(prefix)
    if extracted_name:
        return extracted_name
    raise CompileInputError(f"SQL test '{file_label}' must use {label} to identify a target")


def _validate_ceremonial_select(*, sql: str, start: int, file_label: str) -> None:
    index: int = _skip_ignorable(sql=sql, start=start)
    select_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="SELECT")
    if select_end is None:
        raise CompileInputError(_ceremonial_select_error(file_label))
    index = _skip_ignorable(sql=sql, start=select_end)
    if index >= len(sql) or sql[index] != "1":
        raise CompileInputError(_ceremonial_select_error(file_label))
    index = _skip_ignorable(sql=sql, start=index + 1)
    if index < len(sql) and sql[index] == ";":
        index = _skip_ignorable(sql=sql, start=index + 1)
    if index != len(sql):
        raise CompileInputError(_ceremonial_select_error(file_label))


def _ceremonial_select_error(file_label: str) -> str:
    return f"SQL test '{file_label}' must end with a ceremonial top-level `SELECT 1` after its CTEs"


def _consume_keyword(*, sql: str, start: int, keyword: str, file_label: str) -> int:
    keyword_end: int | None = _try_consume_keyword(sql=sql, start=start, keyword=keyword)
    if keyword_end is not None:
        return keyword_end
    if keyword == "WITH":
        raise CompileInputError(
            f"SQL test '{file_label}' must declare mock CTEs and one __expected__<model> "
            "CTE before `SELECT 1`"
        )
    raise CompileInputError(f"SQL test '{file_label}' expected keyword {keyword}")


def _try_consume_keyword(*, sql: str, start: int, keyword: str) -> int | None:
    keyword_end: int = start + len(keyword)
    if sql[start:keyword_end].upper() != keyword:
        return None
    if keyword_end < len(sql) and is_identifier_character(sql[keyword_end]):
        return None
    if start > 0 and is_identifier_character(sql[start - 1]):
        return None
    return keyword_end


def _read_identifier(*, sql: str, start: int, file_label: str) -> tuple[str, int]:
    if start >= len(sql) or not is_identifier_start(sql[start]):
        raise CompileInputError(f"SQL test '{file_label}' expected a CTE name")
    index: int = start + 1
    while index < len(sql) and is_identifier_character(sql[index]):
        index += 1
    return sql[start:index], index


def _skip_ignorable(*, sql: str, start: int) -> int:
    index: int = start
    while index < len(sql):
        if sql[index].isspace():
            index += 1
            continue
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        return index
    return index
