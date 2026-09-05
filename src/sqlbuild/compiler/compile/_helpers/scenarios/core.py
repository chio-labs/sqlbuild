"""SQL-native scenario compile-semantic extraction helpers."""

from __future__ import annotations

from functools import lru_cache

from sqlbuild.compiler.compile._helpers.analysis.ctes import (
    extract_top_level_ctes_with_sql_analysis,
)
from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    _consume_keyword,
    _read_identifier,
    _require_prefixed_name,
    _skip_ignorable,
    _try_consume_keyword,
    _validate_ceremonial_select,
)
from sqlbuild.compiler.compile.constants import (
    ASSERT_SCENARIO_CTE_PREFIX,
    DBT_REF_TEST_CTE_PREFIX,
    EXPECTED_TEST_CTE_PREFIX,
    MACRO_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
    SQL_ARGUMENT_SEPARATOR_TOKEN,
    SQL_OPEN_PAREN_TOKEN,
    SQL_WITH_KEYWORD,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlScenarioCte,
    CompileSqlScenarioCtes,
)
from sqlbuild.compiler.sql_analysis.main._find_matching_paren import find_matching_paren

_CONTEXT: str = "SQL scenario"


def extract_sql_scenario_ctes(*, sql: str, file_label: str) -> CompileSqlScenarioCtes:
    """Extract top-level SQL-native scenario fixture, expected, and assertion CTEs."""

    try:
        ctes: tuple[CompileSqlScenarioCte, ...] = _extract_sql_scenario_ctes_with_scanner(
            sql=sql,
            file_label=file_label,
        )
    except CompileInputError as scanner_error:
        cte_values: tuple[tuple[str, str], ...] | None = extract_top_level_ctes_with_sql_analysis(
            sql=sql,
            file_label=file_label,
            context_label="SQL scenario",
        )
        if cte_values is None:
            raise scanner_error from None
        ctes = tuple(CompileSqlScenarioCte(name=name, sql_body=body) for name, body in cte_values)
    return _classify_sql_scenario_ctes(ctes=ctes, file_label=file_label)


def extract_sql_scenario_expected_model_names(*, sql: str, file_label: str) -> tuple[str, ...]:
    """Extract explicit expected-model relationships without inspecting CTE bodies."""

    start: int = _skip_ignorable(sql=sql, start=0)
    if _try_consume_keyword(sql=sql, start=start, keyword=SQL_WITH_KEYWORD) is None:
        return ()
    ctes: tuple[CompileSqlScenarioCte, ...] = _extract_sql_scenario_ctes_with_scanner(
        sql=sql,
        file_label=file_label,
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


@lru_cache(maxsize=4096)
def _extract_sql_scenario_ctes_with_scanner(
    *, sql: str, file_label: str
) -> tuple[CompileSqlScenarioCte, ...]:
    index: int = _skip_ignorable(sql=sql, start=0)
    index = _consume_keyword(sql=sql, start=index, keyword="WITH", file_label=file_label)
    index = _skip_ignorable(sql=sql, start=index)
    recursive_end: int | None = _try_consume_keyword(sql=sql, start=index, keyword="RECURSIVE")
    if recursive_end is not None:
        index = _skip_ignorable(sql=sql, start=recursive_end)

    ctes: list[CompileSqlScenarioCte] = []
    seen_cte_names: set[str] = set()
    while True:
        cte_name, index = _read_identifier(sql=sql, start=index, file_label=file_label)
        if cte_name in seen_cte_names:
            raise CompileInputError(
                f"SQL scenario '{file_label}' defines duplicate CTE '{cte_name}'"
            )
        seen_cte_names.add(cte_name)

        index = _skip_ignorable(sql=sql, start=index)
        if index < len(sql) and sql[index] == SQL_OPEN_PAREN_TOKEN:
            index = find_matching_paren(sql=sql, open_paren_index=index, context=_CONTEXT) + 1
            index = _skip_ignorable(sql=sql, start=index)
        index = _consume_keyword(sql=sql, start=index, keyword="AS", file_label=file_label)
        index = _skip_ignorable(sql=sql, start=index)
        if index >= len(sql) or sql[index] != SQL_OPEN_PAREN_TOKEN:
            raise CompileInputError(
                f"SQL scenario '{file_label}' CTE '{cte_name}' must use AS (...)"
            )
        cte_body_start: int = index + 1
        cte_body_end: int = find_matching_paren(sql=sql, open_paren_index=index, context=_CONTEXT)
        ctes.append(
            CompileSqlScenarioCte(
                name=cte_name,
                sql_body=sql[cte_body_start:cte_body_end].strip(),
            )
        )
        index = _skip_ignorable(sql=sql, start=cte_body_end + 1)
        if index < len(sql) and sql[index] == SQL_ARGUMENT_SEPARATOR_TOKEN:
            index = _skip_ignorable(sql=sql, start=index + 1)
            continue
        break

    _validate_ceremonial_select(sql=sql, start=index, file_label=file_label)
    return tuple(ctes)


def _classify_sql_scenario_ctes(
    *, ctes: tuple[CompileSqlScenarioCte, ...], file_label: str
) -> CompileSqlScenarioCtes:
    authored_ctes: list[CompileSqlScenarioCte] = []
    expected_ctes: list[CompileSqlScenarioCte] = []
    assertion_ctes: list[CompileSqlScenarioCte] = []
    source_fixture_names: list[str] = []
    ref_fixture_names: list[str] = []
    seed_fixture_names: list[str] = []
    dbt_ref_fixture_names: list[str] = []
    expected_model_names: list[str] = []
    assertion_names: list[str] = []

    cte: CompileSqlScenarioCte
    for cte in ctes:
        if cte.name.startswith(SOURCE_TEST_CTE_PREFIX):
            source_fixture_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=SOURCE_TEST_CTE_PREFIX,
                    label="__source__<source>",
                    file_label=file_label,
                )
            )
            authored_ctes.append(cte)
            continue
        if cte.name.startswith(REF_TEST_CTE_PREFIX):
            ref_fixture_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=REF_TEST_CTE_PREFIX,
                    label="__ref__<model>",
                    file_label=file_label,
                )
            )
            authored_ctes.append(cte)
            continue
        if cte.name.startswith(SEED_TEST_CTE_PREFIX):
            seed_fixture_names.append(
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
            dbt_ref_fixture_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=DBT_REF_TEST_CTE_PREFIX,
                    label="__dbt_ref__<model> or __dbt_ref__<package>__<model>",
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
            expected_ctes.append(cte)
            continue
        if cte.name.startswith(ASSERT_SCENARIO_CTE_PREFIX):
            assertion_names.append(
                _require_prefixed_name(
                    cte_name=cte.name,
                    prefix=ASSERT_SCENARIO_CTE_PREFIX,
                    label="__assert__<assertion>",
                    file_label=file_label,
                )
            )
            assertion_ctes.append(cte)
            continue
        if cte.name.startswith(MACRO_TEST_CTE_PREFIX):
            raise CompileInputError(
                f"SQL scenario '{file_label}' does not support macro mock CTE '{cte.name}'. "
                "Scenarios run real project macros; use SQL unit tests for macro mocks."
            )
        authored_ctes.append(cte)

    if (
        not source_fixture_names
        and not ref_fixture_names
        and not seed_fixture_names
        and not dbt_ref_fixture_names
    ):
        raise CompileInputError(
            f"SQL scenario '{file_label}' must define at least one __source__*, __ref__*, "
            "__seed__*, or __dbt_ref__* fixture CTE"
        )
    if not expected_model_names and not assertion_names:
        raise CompileInputError(
            f"SQL scenario '{file_label}' must define at least one __expected__<model> or "
            "__assert__<assertion> CTE"
        )
    return CompileSqlScenarioCtes(
        authored_ctes=tuple(authored_ctes),
        expected_ctes=tuple(expected_ctes),
        assertion_ctes=tuple(assertion_ctes),
        source_fixture_names=tuple(source_fixture_names),
        ref_fixture_names=tuple(ref_fixture_names),
        seed_fixture_names=tuple(seed_fixture_names),
        dbt_ref_fixture_names=tuple(dbt_ref_fixture_names),
        expected_model_names=tuple(expected_model_names),
        assertion_names=tuple(assertion_names),
    )
