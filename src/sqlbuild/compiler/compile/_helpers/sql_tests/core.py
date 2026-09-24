"""SQL-native test compile-semantic extraction helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sqlbuild.compiler.compile._helpers.analysis.ctes import (
    extract_top_level_ctes_with_sql_analysis,
)
from sqlbuild.compiler.compile._helpers.analysis.tests import (
    extract_expected_branch_column_names_with_sql_analysis,
)
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile._helpers.render.macros import find_macro_call_names
from sqlbuild.compiler.compile._helpers.sql_tests.empty_fixture import is_empty_fixture_query
from sqlbuild.compiler.compile.constants import (
    ASSERT_TEST_CTE_PREFIX,
    DBT_REF_TEST_CTE_PREFIX,
    DEFAULT_SQL_TEST_MODE,
    EXPECTED_TEST_CTE_PREFIX,
    MACRO_ACTUAL_TEST_CTE_NAME,
    MACRO_EXPECTED_TEST_CTE_NAME,
    MACRO_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    RESERVED_SQL_TEST_CTE_NAMES,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
    SQL_ARGUMENT_SEPARATOR_TOKEN,
    SQL_CEREMONIAL_SELECT_VALUE,
    SQL_OPEN_PAREN_TOKEN,
    SQL_SINGLE_QUOTE_TOKEN,
    SQL_STATEMENT_TERMINATOR_TOKEN,
    SQL_WILDCARD_TOKEN,
    SQL_WITH_KEYWORD,
    TABLE_FN_ACTUAL_TEST_CTE_NAME,
    TABLE_FN_EXPECTED_TEST_CTE_NAME,
    TABLE_FN_TEST_CTE_PREFIX,
    UDF_ACTUAL_TEST_CTE_NAME,
    UDF_EXPECTED_TEST_CTE_NAME,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileDirectLogicSqlTestCtes,
    CompileModelSqlTestCtes,
    CompileSqlReference,
    CompileSqlScenarioCte,
    CompileSqlTestCte,
    CompileSqlTestCtes,
)
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main._find_matching_paren import find_matching_paren
from sqlbuild.compiler.sql_analysis.main._is_identifier_character import (
    is_identifier_character,
)
from sqlbuild.compiler.sql_analysis.main._is_identifier_start import is_identifier_start
from sqlbuild.compiler.sql_analysis.main._iter_code_positions import iter_code_positions
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.compiler.sql_analysis.main._skip_quoted_text import (
    skip_quoted_text,
)
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_CONTEXT: str = "SQL test"
_SQL_TEST_WITH_REQUIREMENT: str = "mock CTEs and one __expected__<model> CTE"
_DIRECT_DEPENDENCY_PATH_LENGTH: int = 2
_SQL_IDENTIFIER_QUOTE_TOKENS: frozenset[str] = frozenset({'"', "`"})


@dataclass(frozen=True)
class _DirectLogicModeSpec:
    mode: SqlTestMode
    actual_cte_name: str
    expected_cte_name: str
    foreign_ctes: tuple[tuple[frozenset[str], str], ...]


_MACRO_TEST_CTE_NAMES: frozenset[str] = frozenset(
    {MACRO_ACTUAL_TEST_CTE_NAME, MACRO_EXPECTED_TEST_CTE_NAME}
)
_UDF_TEST_CTE_NAMES: frozenset[str] = frozenset(
    {UDF_ACTUAL_TEST_CTE_NAME, UDF_EXPECTED_TEST_CTE_NAME}
)
_TABLE_FN_TEST_CTE_NAMES: frozenset[str] = frozenset(
    {TABLE_FN_ACTUAL_TEST_CTE_NAME, TABLE_FN_EXPECTED_TEST_CTE_NAME}
)
_DIRECT_LOGIC_MODE_SPECS: dict[SqlTestMode, _DirectLogicModeSpec] = {
    SqlTestMode.MACRO: _DirectLogicModeSpec(
        mode=SqlTestMode.MACRO,
        actual_cte_name=MACRO_ACTUAL_TEST_CTE_NAME,
        expected_cte_name=MACRO_EXPECTED_TEST_CTE_NAME,
        foreign_ctes=(
            (_UDF_TEST_CTE_NAMES, "UDF-test"),
            (_TABLE_FN_TEST_CTE_NAMES, "table_fn-test"),
        ),
    ),
    SqlTestMode.UDF: _DirectLogicModeSpec(
        mode=SqlTestMode.UDF,
        actual_cte_name=UDF_ACTUAL_TEST_CTE_NAME,
        expected_cte_name=UDF_EXPECTED_TEST_CTE_NAME,
        foreign_ctes=(
            (_MACRO_TEST_CTE_NAMES, "macro-test"),
            (_TABLE_FN_TEST_CTE_NAMES, "table_fn-test"),
        ),
    ),
    SqlTestMode.TABLE_FN: _DirectLogicModeSpec(
        mode=SqlTestMode.TABLE_FN,
        actual_cte_name=TABLE_FN_ACTUAL_TEST_CTE_NAME,
        expected_cte_name=TABLE_FN_EXPECTED_TEST_CTE_NAME,
        foreign_ctes=((_MACRO_TEST_CTE_NAMES | _UDF_TEST_CTE_NAMES, "another direct-logic"),),
    ),
}


def extract_sql_test_ctes(
    *, sql: str, file_label: str, mode: SqlTestMode = DEFAULT_SQL_TEST_MODE
) -> CompileSqlTestCtes:
    """Extract top-level SQL-native test mock and expected CTEs."""

    ctes: tuple[CompileSqlTestCte, ...] = extract_unclassified_sql_test_ctes(
        sql=sql,
        file_label=file_label,
    )
    return classify_sql_test_ctes(ctes=ctes, file_label=file_label, mode=mode)


def extract_unclassified_sql_test_ctes(
    *, sql: str, file_label: str
) -> tuple[CompileSqlTestCte, ...]:
    """Extract raw top-level CTEs before mode-specific classification."""

    try:
        ctes: tuple[CompileSqlTestCte, ...] = extract_top_level_ctes_with_scanner(
            sql=sql,
            file_label=file_label,
            context_label=_CONTEXT,
            with_requirement=_SQL_TEST_WITH_REQUIREMENT,
            cte_type=CompileSqlTestCte,
        )
    except CompileInputError as scanner_error:
        cte_values: tuple[tuple[str, str], ...] | None = extract_top_level_ctes_with_sql_analysis(
            sql=sql,
            file_label=file_label,
            context_label="SQL test",
        )
        if cte_values is None:
            raise scanner_error from None
        ctes = tuple(CompileSqlTestCte(name=name, sql_body=body) for name, body in cte_values)
    return ctes


def classify_sql_test_ctes(
    *, ctes: tuple[CompileSqlTestCte, ...], file_label: str, mode: SqlTestMode
) -> CompileSqlTestCtes:
    """Apply mode-specific validation to extracted SQL test CTEs."""

    return _classify_sql_test_ctes(ctes=ctes, file_label=file_label, mode=mode)


def extract_sql_test_expected_model_names(
    *, sql: str, file_label: str, mode: SqlTestMode = DEFAULT_SQL_TEST_MODE
) -> tuple[str, ...]:
    """Extract explicit expected-model relationships without inspecting CTE bodies."""

    if mode is not SqlTestMode.MODEL:
        return ()
    start: int = _skip_ignorable(sql=sql, start=0)
    if _try_consume_keyword(sql=sql, start=start, keyword=SQL_WITH_KEYWORD) is None:
        return ()
    ctes: tuple[CompileSqlTestCte, ...] = extract_top_level_ctes_with_scanner(
        sql=sql,
        file_label=file_label,
        context_label=_CONTEXT,
        with_requirement=_SQL_TEST_WITH_REQUIREMENT,
        cte_type=CompileSqlTestCte,
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


def extract_assertion_target_model_names(*, assertion_sql: tuple[str, ...]) -> tuple[str, ...]:
    """Extract assertion model targets in authored order using canonical references."""

    targets: list[str] = []
    for sql in assertion_sql:
        targets.extend(
            reference.ref_name
            for reference in extract_sql_references(sql)
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
) -> tuple[CteT, ...]:
    """Scan top-level `WITH` CTEs followed by the ceremonial `SELECT 1` of a test file."""

    with_end: int | None = _try_consume_keyword(
        sql=sql, start=_skip_ignorable(sql=sql, start=0), keyword=SQL_WITH_KEYWORD
    )
    if with_end is None:
        raise CompileInputError(
            f"{context_label} '{file_label}' must declare {with_requirement} before `SELECT 1`"
        )
    index: int = _skip_ignorable(sql=sql, start=with_end)
    recursive_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="RECURSIVE")
    if recursive_end is not None:
        index = _skip_ignorable(sql=sql, start=recursive_end)

    ctes: list[CteT] = []
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

        index = _skip_ignorable(sql=sql, start=index)
        if index < len(sql) and sql[index] == SQL_OPEN_PAREN_TOKEN:
            index = find_matching_paren(sql=sql, open_paren_index=index, context=context_label) + 1
            index = _skip_ignorable(sql=sql, start=index)
        index = _consume_keyword(
            sql=sql,
            start=index,
            keyword="AS",
            file_label=file_label,
            context_label=context_label,
        )
        index = _skip_ignorable(sql=sql, start=index)
        if index >= len(sql) or sql[index] != SQL_OPEN_PAREN_TOKEN:
            raise CompileInputError(
                f"{context_label} '{file_label}' CTE '{cte_name}' must use AS (...)"
            )
        cte_body_start: int = index + 1
        cte_body_end: int = find_matching_paren(
            sql=sql, open_paren_index=index, context=context_label
        )
        ctes.append(cte_type(name=cte_name, sql_body=sql[cte_body_start:cte_body_end].strip()))
        index = _skip_ignorable(sql=sql, start=cte_body_end + 1)
        if index < len(sql) and sql[index] == SQL_ARGUMENT_SEPARATOR_TOKEN:
            index = _skip_ignorable(sql=sql, start=index + 1)
            continue
        break

    _validate_ceremonial_select(
        sql=sql,
        start=index,
        file_label=file_label,
        context_label=context_label,
    )
    return tuple(ctes)


def _classify_sql_test_ctes(
    *, ctes: tuple[CompileSqlTestCte, ...], file_label: str, mode: SqlTestMode
) -> CompileSqlTestCtes:
    match mode:
        case SqlTestMode.MODEL:
            return _classify_model_sql_test_ctes(ctes=ctes, file_label=file_label)
        case SqlTestMode.MACRO | SqlTestMode.UDF | SqlTestMode.TABLE_FN:
            return _classify_direct_logic_sql_test_ctes(
                ctes=ctes, file_label=file_label, spec=_DIRECT_LOGIC_MODE_SPECS[mode]
            )
        case _:
            raise CompileInputError(f"SQL test '{file_label}' has unsupported mode '{mode}'")


def _classify_direct_logic_sql_test_ctes(
    *, ctes: tuple[CompileSqlTestCte, ...], file_label: str, spec: _DirectLogicModeSpec
) -> CompileSqlTestCtes:
    mode: str = spec.mode.value
    authored_ctes: list[CompileSqlTestCte] = []
    actual_cte: CompileSqlTestCte | None = None
    expected_cte: CompileSqlTestCte | None = None

    cte: CompileSqlTestCte
    for cte in ctes:
        if cte.name == spec.actual_cte_name:
            if actual_cte is not None:
                raise CompileInputError(
                    f"SQL test '{file_label}' mode '{mode}' must define exactly one "
                    f"{spec.actual_cte_name} CTE"
                )
            actual_cte = cte
            continue
        if cte.name == spec.expected_cte_name:
            if expected_cte is not None:
                raise CompileInputError(
                    f"SQL test '{file_label}' mode '{mode}' must define exactly one "
                    f"{spec.expected_cte_name} CTE"
                )
            _validate_expected_cte_query(cte=cte, file_label=file_label, label=cte.name)
            expected_cte = cte
            continue
        if _is_model_mode_cte(cte.name):
            raise CompileInputError(
                f"SQL test '{file_label}' is mode '{mode}' but defines model-test CTE '{cte.name}'"
            )
        foreign_names: frozenset[str]
        foreign_label: str
        for foreign_names, foreign_label in spec.foreign_ctes:
            if cte.name in foreign_names:
                raise CompileInputError(
                    f"SQL test '{file_label}' is mode '{mode}' but defines {foreign_label} CTE "
                    f"'{cte.name}'"
                )
        if cte.name in RESERVED_SQL_TEST_CTE_NAMES:
            raise CompileInputError(
                f"SQL test '{file_label}' uses reserved helper CTE name '{cte.name}'"
            )
        authored_ctes.append(cte)

    if actual_cte is None or expected_cte is None:
        raise CompileInputError(
            f"SQL test '{file_label}' mode '{mode}' must define exactly one "
            f"{spec.actual_cte_name} CTE and exactly one "
            f"{spec.expected_cte_name} CTE"
        )
    if spec.mode is SqlTestMode.MACRO:
        _validate_macro_test_bodies(
            helper_ctes=tuple(authored_ctes), expected_cte=expected_cte, file_label=file_label
        )
    else:
        _validate_call_free_direct_logic_bodies(
            helper_ctes=tuple(authored_ctes),
            expected_cte=expected_cte,
            file_label=file_label,
            mode=spec.mode,
            actual_cte_name=spec.actual_cte_name,
        )
    return CompileSqlTestCtes(
        mode=spec.mode,
        payload=CompileDirectLogicSqlTestCtes(
            mode=spec.mode,
            helper_ctes=tuple(authored_ctes),
            actual_cte=actual_cte,
            expected_cte=expected_cte,
        ),
    )


def _classify_model_sql_test_ctes(
    *, ctes: tuple[CompileSqlTestCte, ...], file_label: str
) -> CompileSqlTestCtes:
    validate_independent_expected_and_assertion_ctes(
        ctes=ctes,
        expected_prefix=EXPECTED_TEST_CTE_PREFIX,
        assertion_prefix=ASSERT_TEST_CTE_PREFIX,
        file_label=file_label,
        context_label="SQL test",
    )
    authored_ctes: list[CompileSqlTestCte] = []
    macro_mocks: dict[str, str] = {}
    mock_model_names: list[str] = []
    mock_source_names: list[str] = []
    mock_seed_names: list[str] = []
    mock_dbt_ref_names: list[str] = []
    mock_table_function_names: list[str] = []
    expected_ctes: list[CompileSqlTestCte] = []
    expected_model_names: list[str] = []
    assertion_ctes: list[CompileSqlTestCte] = []
    assertion_names: list[str] = []

    cte: CompileSqlTestCte
    for cte in ctes:
        if cte.name in {MACRO_ACTUAL_TEST_CTE_NAME, MACRO_EXPECTED_TEST_CTE_NAME}:
            raise CompileInputError(
                f"SQL test '{file_label}' is mode '{DEFAULT_SQL_TEST_MODE.value}' but defines "
                f"macro-test CTE '{cte.name}'; use TEST (mode {SqlTestMode.MACRO.value})"
            )
        if cte.name in {UDF_ACTUAL_TEST_CTE_NAME, UDF_EXPECTED_TEST_CTE_NAME}:
            raise CompileInputError(
                f"SQL test '{file_label}' is mode '{DEFAULT_SQL_TEST_MODE.value}' but defines "
                f"UDF-test CTE '{cte.name}'; use TEST (mode {SqlTestMode.UDF.value})"
            )
        if cte.name in {TABLE_FN_ACTUAL_TEST_CTE_NAME, TABLE_FN_EXPECTED_TEST_CTE_NAME}:
            raise CompileInputError(
                f"SQL test '{file_label}' is mode '{DEFAULT_SQL_TEST_MODE.value}' but defines "
                f"table_fn-test CTE '{cte.name}'; use TEST (mode {SqlTestMode.TABLE_FN.value})"
            )
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
        if cte.name.startswith(DBT_REF_TEST_CTE_PREFIX):
            mock_dbt_ref_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=DBT_REF_TEST_CTE_PREFIX,
                    label="__dbt_ref__<model> or __dbt_ref__<package>__<model>",
                    file_label=file_label,
                )
            )
            authored_ctes.append(cte)
            continue
        if cte.name.startswith(TABLE_FN_TEST_CTE_PREFIX):
            mock_table_function_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=TABLE_FN_TEST_CTE_PREFIX,
                    label="__table_fn__<function>",
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
            _validate_expected_cte_query(
                cte=cte,
                file_label=file_label,
                allow_empty_fixture=True,
            )
            expected_ctes.append(cte)
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

    mock_target_names: tuple[str, ...] = (
        *mock_model_names,
        *mock_source_names,
        *mock_seed_names,
        *mock_dbt_ref_names,
        *mock_table_function_names,
    )
    if not mock_target_names:
        raise CompileInputError(
            f"SQL test '{file_label}' must define at least one __ref__*, __source__*, "
            "__seed__*, __dbt_ref__*, or __table_fn__* mock CTE"
        )
    check_names: tuple[str, ...] = (*expected_model_names, *assertion_names)
    if not check_names:
        raise CompileInputError(
            f"SQL test '{file_label}' must define at least one __expected__<model> or "
            "__assert__<assertion> CTE"
        )
    model_payload: CompileModelSqlTestCtes = CompileModelSqlTestCtes(
        authored_ctes=tuple(authored_ctes),
        macro_mocks=macro_mocks,
        mock_model_names=tuple(mock_model_names),
        mock_source_names=tuple(mock_source_names),
        mock_seed_names=tuple(mock_seed_names),
        mock_dbt_ref_names=tuple(mock_dbt_ref_names),
        mock_table_function_names=tuple(mock_table_function_names),
        expected_ctes=tuple(expected_ctes),
        expected_model_names=tuple(expected_model_names),
        assertion_ctes=tuple(assertion_ctes),
        assertion_names=tuple(assertion_names),
    )
    return CompileSqlTestCtes(mode=SqlTestMode.MODEL, payload=model_payload)


def _is_model_mode_cte(cte_name: str) -> bool:
    return cte_name.startswith(
        (
            MACRO_TEST_CTE_PREFIX,
            REF_TEST_CTE_PREFIX,
            SOURCE_TEST_CTE_PREFIX,
            SEED_TEST_CTE_PREFIX,
            DBT_REF_TEST_CTE_PREFIX,
            TABLE_FN_TEST_CTE_PREFIX,
            EXPECTED_TEST_CTE_PREFIX,
            ASSERT_TEST_CTE_PREFIX,
        )
    )


def _validate_macro_test_bodies(
    *,
    helper_ctes: tuple[CompileSqlTestCte, ...],
    expected_cte: CompileSqlTestCte,
    file_label: str,
) -> None:
    helper_cte: CompileSqlTestCte
    for helper_cte in helper_ctes:
        macro_names: tuple[str, ...] = find_macro_call_names(helper_cte.sql_body)
        if macro_names:
            raise CompileInputError(
                f"SQL test '{file_label}' mode 'macro' helper CTE '{helper_cte.name}' "
                "must not call macros; call macros only in __macro_actual__"
            )
    expected_macro_names: tuple[str, ...] = find_macro_call_names(expected_cte.sql_body)
    if expected_macro_names:
        raise CompileInputError(
            f"SQL test '{file_label}' mode 'macro' CTE {MACRO_EXPECTED_TEST_CTE_NAME} "
            "must not call macros"
        )


def _validate_call_free_direct_logic_bodies(
    *,
    helper_ctes: tuple[CompileSqlTestCte, ...],
    expected_cte: CompileSqlTestCte,
    file_label: str,
    mode: SqlTestMode,
    actual_cte_name: str,
) -> None:
    helper_cte: CompileSqlTestCte
    for helper_cte in helper_ctes:
        _validate_no_direct_logic_calls(
            sql=helper_cte.sql_body,
            file_label=file_label,
            mode=mode,
            cte_label=f"helper CTE '{helper_cte.name}'",
            allowed_location=actual_cte_name,
        )
    _validate_no_direct_logic_calls(
        sql=expected_cte.sql_body,
        file_label=file_label,
        mode=mode,
        cte_label=f"CTE {expected_cte.name}",
        allowed_location=actual_cte_name,
    )


def _validate_no_direct_logic_calls(
    *, sql: str, file_label: str, mode: SqlTestMode, cte_label: str, allowed_location: str
) -> None:
    macro_names: tuple[str, ...] = find_macro_call_names(sql)
    if macro_names:
        raise CompileInputError(
            f"SQL test '{file_label}' mode '{mode.value}' {cte_label} must not call macros"
        )
    references: tuple[CompileSqlReference, ...] = extract_sql_references(sql)
    reference: CompileSqlReference | None = next(
        (
            item
            for item in references
            if item.ref_kind in {SqlReferenceKind.UDF, SqlReferenceKind.TABLE_FUNCTION}
        ),
        None,
    )
    if reference is not None:
        reference_kind: SqlReferenceKind = SqlReferenceKind(reference.ref_kind)
        raise CompileInputError(
            f"SQL test '{file_label}' mode '{mode.value}' {cte_label} must not call "
            f"{reference_kind.value}; call reusable logic only in {allowed_location}"
        )


def _extract_macro_mock_value(*, cte: CompileSqlTestCte, file_label: str) -> str:
    """Extract the single SQL string literal value from a __macro__ CTE."""

    body: str = cte.sql_body.strip()
    index: int = _skip_ignorable(sql=body, start=0)
    index = _consume_keyword(sql=body, start=index, keyword="SELECT", file_label=file_label)
    index = _skip_ignorable(sql=body, start=index)
    if index >= len(body) or body[index] != SQL_SINGLE_QUOTE_TOKEN:
        raise CompileInputError(
            f"SQL test '{file_label}' macro mock '{cte.name}' must be a single SELECT string "
            "literal, for example SELECT '''US'''"
        )
    value: str
    value, index = _read_sql_string_literal(sql=body, start=index)
    index = _skip_ignorable(sql=body, start=index)
    if index < len(body) and body[index] == SQL_STATEMENT_TERMINATOR_TOKEN:
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
        if char == SQL_SINGLE_QUOTE_TOKEN:
            if index + 1 < len(sql) and sql[index + 1] == SQL_SINGLE_QUOTE_TOKEN:
                value_parts.append("'")
                index += 2
                continue
            return "".join(value_parts), index + 1
        value_parts.append(char)
        index += 1
    raise CompileInputError("SQL test macro mock has an unterminated string literal")


def _validate_expected_cte_query(
    *,
    cte: CompileSqlTestCte,
    file_label: str,
    label: str = "__expected__<model>",
    allow_empty_fixture: bool = False,
) -> None:
    if allow_empty_fixture and is_empty_fixture_query(cte.sql_body):
        return
    if _contains_select_star(cte.sql_body):
        raise CompileInputError(f"SQL test '{file_label}' must not use SELECT * in {label} CTEs")
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
    sql_analysis_column_names: tuple[tuple[str, ...], ...] | None = (
        extract_expected_branch_column_names_with_sql_analysis(sql=sql, file_label=file_label)
    )
    if sql_analysis_column_names is not None:
        return sql_analysis_column_names
    branches: tuple[str, ...] = _split_set_operation_branches(sql)
    return tuple(
        _extract_expected_select_column_names(branch_sql=branch, file_label=file_label)
        for branch in branches
    )


def _split_set_operation_branches(sql: str) -> tuple[str, ...]:
    branches: list[str] = []
    branch_start: int = 0
    resume: int = 0
    index: int
    depth: int
    for index, depth in iter_code_positions(sql=sql, context=_CONTEXT):
        if index < resume or depth != 0:
            continue
        union_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="UNION")
        if union_end is None:
            continue
        branch_sql: str = sql[branch_start:index].strip()
        if branch_sql:
            branches.append(branch_sql)
        resume = _skip_ignorable(sql=sql, start=union_end)
        quantifier_end: int | None = _try_consume_keyword(
            sql=sql, start=resume, keyword="ALL"
        ) or _try_consume_keyword(sql=sql, start=resume, keyword="DISTINCT")
        if quantifier_end is not None:
            resume = _skip_ignorable(sql=sql, start=quantifier_end)
        branch_start = resume

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
    index: int
    depth: int
    for index, depth in iter_code_positions(sql=sql[start:], context=_CONTEXT):
        if (
            depth == 0
            and _try_consume_keyword(sql=sql, start=start + index, keyword="FROM") is not None
        ):
            return start + index
    return len(sql)


def _split_top_level_commas(raw_value: str) -> tuple[str, ...]:
    values: list[str] = []
    value_start: int = 0
    index: int
    depth: int
    for index, depth in iter_code_positions(sql=raw_value, context=_CONTEXT):
        if depth == 0 and raw_value[index] == SQL_ARGUMENT_SEPARATOR_TOKEN:
            item: str = raw_value[value_start:index].strip()
            if item:
                values.append(item)
            value_start = index + 1

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
    last_alias_name: str | None = None
    index: int
    depth: int
    for index, depth in iter_code_positions(sql=expression, context=_CONTEXT):
        if depth != 0:
            continue
        as_end: int | None = _try_consume_keyword(sql=expression, start=index, keyword="AS")
        if as_end is None:
            continue
        alias_index: int = _skip_ignorable(sql=expression, start=as_end)
        if alias_index < len(expression) and is_identifier_start(expression[alias_index]):
            alias_name, alias_end = _read_identifier(
                sql=expression,
                start=alias_index,
                file_label="projection",
            )
            if not expression[alias_end:].strip():
                last_alias_name = alias_name
    return last_alias_name


def _is_simple_identifier(value: str) -> bool:
    if not value or not is_identifier_start(value[0]):
        return False
    return all(is_identifier_character(character) for character in value[1:])


def _contains_select_star(sql: str) -> bool:
    index: int
    for index, _depth in iter_code_positions(sql=sql, context=_CONTEXT):
        select_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="SELECT")
        if select_end is None:
            continue
        value_index: int = _skip_ignorable(sql=sql, start=select_end)
        if value_index < len(sql) and sql[value_index] == SQL_WILDCARD_TOKEN:
            return True
    return False


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
    context_label: str = _CONTEXT,
) -> None:
    if _is_ceremonial_select_statement(sql=sql, start=start):
        return
    raise CompileInputError(
        f"{context_label} '{file_label}' must end with a ceremonial top-level `SELECT 1` "
        "after its CTEs"
    )


def _is_ceremonial_select_statement(*, sql: str, start: int) -> bool:
    index: int = _skip_ignorable(sql=sql, start=start)
    select_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="SELECT")
    if select_end is None:
        return False
    index = _skip_ignorable(sql=sql, start=select_end)
    if index >= len(sql) or sql[index] != SQL_CEREMONIAL_SELECT_VALUE:
        return False
    index = _skip_ignorable(sql=sql, start=index + 1)
    return _is_statement_end(sql=sql, start=index)


def _is_statement_end(*, sql: str, start: int) -> bool:
    index: int = start
    if index < len(sql) and sql[index] == SQL_STATEMENT_TERMINATOR_TOKEN:
        index = _skip_ignorable(sql=sql, start=index + 1)
    return index == len(sql)


def validate_independent_expected_and_assertion_ctes(
    *,
    ctes: tuple[CompileSqlTestCte | CompileSqlScenarioCte, ...],
    expected_prefix: str,
    assertion_prefix: str,
    file_label: str,
    context_label: str,
) -> None:
    """Reject direct and transitive dependencies between expected and assertion checks."""

    names_by_key: dict[str, str] = {cte.name.casefold(): cte.name for cte in ctes}
    expected_keys: frozenset[str] = frozenset(
        key for key, name in names_by_key.items() if name.startswith(expected_prefix)
    )
    assertion_keys: frozenset[str] = frozenset(
        key for key, name in names_by_key.items() if name.startswith(assertion_prefix)
    )
    for cte in ctes:
        cte_key: str = cte.name.casefold()
        prohibited_prefix: str | None = None
        prohibited_label: str | None = None
        if cte_key in expected_keys:
            prohibited_prefix = assertion_prefix
            prohibited_label = "assertion"
        elif cte_key in assertion_keys:
            prohibited_prefix = expected_prefix
            prohibited_label = "expected result"
        if prohibited_prefix is None or prohibited_label is None:
            continue
        if prohibited_prefix.casefold() not in cte.sql_body.casefold():
            continue
        nested_name: str | None = next(
            (
                name
                for name in _defined_cte_names(sql=cte.sql_body)
                if name.startswith(prohibited_prefix)
            ),
            None,
        )
        if nested_name is not None:
            raise CompileInputError(
                f"{context_label} '{file_label}' check CTE '{cte.name}' must not define "
                f"{prohibited_label} CTE '{nested_name}'; expected results and assertions must "
                "be independent"
            )

    if not expected_keys or not assertion_keys:
        return

    dependencies: dict[str, tuple[str, ...]] = {
        cte.name.casefold(): _known_cte_references(
            sql=cte.sql_body,
            names_by_key=names_by_key,
        )
        for cte in ctes
    }
    for origins, prohibited in (
        (expected_keys, assertion_keys),
        (assertion_keys, expected_keys),
    ):
        for origin in sorted(origins):
            path: tuple[str, ...] | None = _dependency_path(
                origin=origin,
                prohibited=prohibited,
                dependencies=dependencies,
            )
            if path is None:
                continue
            rendered_path: tuple[str, ...] = tuple(names_by_key[key] for key in path)
            through: str = (
                " through " + " -> ".join(f"'{name}'" for name in rendered_path[1:-1])
                if len(rendered_path) > _DIRECT_DEPENDENCY_PATH_LENGTH
                else ""
            )
            raise CompileInputError(
                f"{context_label} '{file_label}' check CTE '{rendered_path[0]}' must not depend "
                f"on '{rendered_path[-1]}'{through}; expected results and assertions must be "
                "independent"
            )


def _defined_cte_names(*, sql: str) -> tuple[str, ...]:
    polyglot_module: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot_module.parse_one(sql, dialect="generic")
    except polyglot_module.PolyglotError:
        return ()

    def collect(value: Any) -> tuple[str, ...]:
        names: list[str] = []
        if isinstance(value, dict):
            ctes: Any = value.get("ctes")
            if isinstance(ctes, list):
                for cte in ctes:
                    if not isinstance(cte, dict):
                        continue
                    alias: Any = cte.get("alias")
                    if not isinstance(alias, dict):
                        continue
                    name: Any = alias.get("name")
                    if isinstance(name, str) and name not in names:
                        names.append(name)
            for child in value.values():
                names.extend(collect(child))
        elif isinstance(value, list):
            for child in value:
                names.extend(collect(child))
        return tuple(dict.fromkeys(names))

    return collect(parsed.to_dict())


def _known_cte_references(*, sql: str, names_by_key: dict[str, str]) -> tuple[str, ...]:
    folded_sql: str = sql.casefold()
    if not any(name in folded_sql for name in names_by_key):
        return ()
    polyglot_module: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot_module.parse_one(sql, dialect="generic")
    except polyglot_module.PolyglotError:
        return _known_cte_identifier_references(sql=sql, names_by_key=names_by_key)
    references: list[str] = []
    for table in parsed.find_all("table"):
        key: str = str(getattr(table, "name", "") or "").casefold()
        if key in names_by_key and key not in references:
            references.append(key)
    return tuple(references)


def _known_cte_identifier_references(*, sql: str, names_by_key: dict[str, str]) -> tuple[str, ...]:
    references: list[str] = []
    index: int = 0
    while index < len(sql):
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql[index] == SQL_SINGLE_QUOTE_TOKEN:
            index = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql[index] in _SQL_IDENTIFIER_QUOTE_TOKENS:
            quote: str = sql[index]
            end: int = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            name: str = sql[index + 1 : end - 1].replace(quote * 2, quote)
            key: str = name.casefold()
            if key in names_by_key and key not in references:
                references.append(key)
            index = end
            continue
        if not is_identifier_start(sql[index]):
            index += 1
            continue
        name, index = _read_identifier(sql=sql, start=index, file_label="check CTE")
        key: str = name.casefold()
        if key in names_by_key and key not in references:
            references.append(key)
    return tuple(references)


def _dependency_path(
    *,
    origin: str,
    prohibited: frozenset[str],
    dependencies: dict[str, tuple[str, ...]],
) -> tuple[str, ...] | None:
    pending: list[tuple[str, ...]] = [(origin,)]
    visited: set[str] = {origin}
    while pending:
        path: tuple[str, ...] = pending.pop(0)
        for dependency in dependencies.get(path[-1], ()):
            candidate: tuple[str, ...] = (*path, dependency)
            if dependency in prohibited:
                return candidate
            if dependency in visited:
                continue
            visited.add(dependency)
            pending.append(candidate)
    return None


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
