"""SQL-native scenario compile-semantic extraction helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.analysis.ctes import (
    extract_top_level_ctes_with_sql_analysis,
)
from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    _require_prefixed_name,
    _skip_ignorable,
    _try_consume_keyword,
    extract_top_level_ctes_with_scanner,
    validate_independent_expected_and_assertion_ctes,
)
from sqlbuild.compiler.compile.constants import (
    ASSERT_SCENARIO_CTE_PREFIX,
    DBT_REF_TEST_CTE_PREFIX,
    EXPECTED_TEST_CTE_PREFIX,
    MACRO_TEST_CTE_PREFIX,
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
    SQL_WITH_KEYWORD,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlScenarioCte,
    CompileSqlScenarioCtes,
)

_CONTEXT: str = "SQL scenario"
_WITH_REQUIREMENT: str = (
    "fixture CTEs and at least one __expected__<model> or __assert__<assertion> CTE"
)


def extract_sql_scenario_ctes(*, sql: str, file_label: str) -> CompileSqlScenarioCtes:
    """Extract top-level SQL-native scenario fixture, expected, and assertion CTEs."""

    try:
        ctes: tuple[CompileSqlScenarioCte, ...] = extract_top_level_ctes_with_scanner(
            sql=sql,
            file_label=file_label,
            context_label=_CONTEXT,
            with_requirement=_WITH_REQUIREMENT,
            cte_type=CompileSqlScenarioCte,
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
    ctes: tuple[CompileSqlScenarioCte, ...] = extract_top_level_ctes_with_scanner(
        sql=sql,
        file_label=file_label,
        context_label=_CONTEXT,
        with_requirement=_WITH_REQUIREMENT,
        cte_type=CompileSqlScenarioCte,
    )
    return tuple(
        _require_prefixed_name(
            cte_name=cte.name,
            prefix=EXPECTED_TEST_CTE_PREFIX,
            label="__expected__<model>",
            file_label=file_label,
            context_label=_CONTEXT,
        )
        for cte in ctes
        if cte.name.startswith(EXPECTED_TEST_CTE_PREFIX)
    )


def _classify_sql_scenario_ctes(
    *, ctes: tuple[CompileSqlScenarioCte, ...], file_label: str
) -> CompileSqlScenarioCtes:
    validate_independent_expected_and_assertion_ctes(
        ctes=ctes,
        expected_prefix=EXPECTED_TEST_CTE_PREFIX,
        assertion_prefix=ASSERT_SCENARIO_CTE_PREFIX,
        file_label=file_label,
        context_label="SQL scenario",
    )
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
                    context_label=_CONTEXT,
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
                    context_label=_CONTEXT,
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
                    context_label=_CONTEXT,
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
                    context_label=_CONTEXT,
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
                    context_label=_CONTEXT,
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
                    context_label=_CONTEXT,
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
