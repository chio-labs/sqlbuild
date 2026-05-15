"""SQL-native scenario compile-semantic extraction helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import (
    ASSERT_SCENARIO_CTE_PREFIX,
    DBT_REF_TEST_CTE_PREFIX,
    EXPECTED_TEST_CTE_PREFIX,
    MACRO_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.sql_scanning import find_matching_paren
from sqlbuild.compiler.compile.helpers.tests import (
    _consume_keyword,
    _read_identifier,
    _require_prefixed_name,
    _skip_ignorable,
    _try_consume_keyword,
    _validate_ceremonial_select,
)
from sqlbuild.compiler.compile.models.core import (
    CompileSqlScenarioCte,
    CompileSqlScenarioCtes,
)

_CONTEXT: str = "SQL scenario"


def extract_sql_scenario_ctes(*, sql: str, file_label: str) -> CompileSqlScenarioCtes:
    """Extract top-level SQL-native scenario fixture, expected, and assertion CTEs."""

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
        if index < len(sql) and sql[index] == "(":
            index = find_matching_paren(sql=sql, open_paren_index=index, context=_CONTEXT) + 1
            index = _skip_ignorable(sql=sql, start=index)
        index = _consume_keyword(sql=sql, start=index, keyword="AS", file_label=file_label)
        index = _skip_ignorable(sql=sql, start=index)
        if index >= len(sql) or sql[index] != "(":
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
        if index < len(sql) and sql[index] == ",":
            index = _skip_ignorable(sql=sql, start=index + 1)
            continue
        break

    _validate_ceremonial_select(sql=sql, start=index, file_label=file_label)
    return _classify_sql_scenario_ctes(ctes=tuple(ctes), file_label=file_label)


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
