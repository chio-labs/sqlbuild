"""SQL-native scenario compile-semantic extraction helpers."""

from __future__ import annotations

from typing import Any

import orjson

import sqlbuild._native as _native
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
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

_CONTEXT: str = "SQL scenario"
_WITH_REQUIREMENT: str = (
    "fixture CTEs and at least one __expected__<model> or __assert__<assertion> CTE"
)


def extract_sql_scenario_ctes(
    *, sql: str, file_label: str, syntax: SqlLexicalSyntax
) -> CompileSqlScenarioCtes:
    """Extract top-level SQL-native scenario fixture, expected, and assertion CTEs."""

    native_ctes: CompileSqlScenarioCtes | None = (
        _native_scenario_ctes(sql=sql, file_label=file_label, syntax=syntax)
        if native_stage_enabled(NativeStage.ATTACHMENTS)
        else None
    )
    if native_ctes is not None:
        return native_ctes
    try:
        ctes: tuple[CompileSqlScenarioCte, ...] = extract_top_level_ctes_with_scanner(
            sql=sql,
            file_label=file_label,
            context_label=_CONTEXT,
            with_requirement=_WITH_REQUIREMENT,
            cte_type=CompileSqlScenarioCte,
            syntax=syntax,
        )
    except CompileInputError as scanner_error:
        polyglot_ctes: tuple[CompileSqlScenarioCte, ...] | None = _polyglot_scenario_ctes(
            sql=sql, file_label=file_label
        )
        if polyglot_ctes is None:
            raise scanner_error from None
        ctes = polyglot_ctes
    return _classify_sql_scenario_ctes(ctes=ctes, file_label=file_label, syntax=syntax)


def _polyglot_scenario_ctes(
    *, sql: str, file_label: str
) -> tuple[CompileSqlScenarioCte, ...] | None:
    cte_values: tuple[tuple[str, str], ...] | None = extract_top_level_ctes_with_sql_analysis(
        sql=sql,
        file_label=file_label,
        context_label=_CONTEXT,
    )
    if cte_values is None:
        return None
    return tuple(CompileSqlScenarioCte(name=name, sql_body=body) for name, body in cte_values)


def _native_scenario_ctes(
    *, sql: str, file_label: str, syntax: SqlLexicalSyntax
) -> CompileSqlScenarioCtes | None:
    """Extract natively with Python's errors, or None where Python must read the scenario."""

    try:
        response: str | None = _native.extract_sql_scenario_json(
            sql, file_label, syntax.native_mapping
        )
    except (TypeError, UnicodeError):
        return None
    if response is None:
        return None
    try:
        return _scenario_from_native_outcome(
            outcome=orjson.loads(response), sql=sql, file_label=file_label, syntax=syntax
        )
    except CompileInputError as error:
        error.bridge_independent = True
        raise


def _scenario_from_native_outcome(
    *, outcome: dict[str, Any], sql: str, file_label: str, syntax: SqlLexicalSyntax
) -> CompileSqlScenarioCtes:
    """Build the native outcome, running only Python's Polyglot steps the native scan leaves."""

    scan_error: str | None = outcome.get("scanError")
    if scan_error is not None:
        polyglot_ctes: tuple[CompileSqlScenarioCte, ...] | None = _polyglot_scenario_ctes(
            sql=sql, file_label=file_label
        )
        if polyglot_ctes is None:
            raise CompileInputError(scan_error)
        return _classify_sql_scenario_ctes(ctes=polyglot_ctes, file_label=file_label, syntax=syntax)
    independence: list[list[str]] | None = outcome.get("independence")
    if independence is not None:
        validate_independent_expected_and_assertion_ctes(
            ctes=_scenario_ctes(independence),
            expected_prefix=EXPECTED_TEST_CTE_PREFIX,
            assertion_prefix=ASSERT_SCENARIO_CTE_PREFIX,
            file_label=file_label,
            context_label=_CONTEXT,
            syntax=syntax,
        )
    error: str | None = outcome.get("error")
    if error is not None:
        raise CompileInputError(error)
    payload: dict[str, list[Any]] = outcome["scenario"]
    return CompileSqlScenarioCtes(
        authored_ctes=_scenario_ctes(payload["authored"]),
        expected_ctes=_scenario_ctes(payload["expected"]),
        assertion_ctes=_scenario_ctes(payload["assertions"]),
        source_fixture_names=tuple(payload["sourceFixtures"]),
        ref_fixture_names=tuple(payload["refFixtures"]),
        seed_fixture_names=tuple(payload["seedFixtures"]),
        dbt_ref_fixture_names=tuple(payload["dbtRefFixtures"]),
        expected_model_names=tuple(payload["expectedModels"]),
        assertion_names=tuple(payload["assertionNames"]),
    )


def _scenario_ctes(values: list[list[str]]) -> tuple[CompileSqlScenarioCte, ...]:
    return tuple(CompileSqlScenarioCte(name=name, sql_body=body) for name, body in values)


def extract_sql_scenario_expected_model_names(
    *, sql: str, file_label: str, syntax: SqlLexicalSyntax
) -> tuple[str, ...]:
    """Extract explicit expected-model relationships without inspecting CTE bodies."""

    start: int = _skip_ignorable(sql=sql, start=0, context_label=_CONTEXT, syntax=syntax)
    if _try_consume_keyword(sql=sql, start=start, keyword=SQL_WITH_KEYWORD) is None:
        return ()
    ctes: tuple[CompileSqlScenarioCte, ...] = extract_top_level_ctes_with_scanner(
        sql=sql,
        file_label=file_label,
        context_label=_CONTEXT,
        with_requirement=_WITH_REQUIREMENT,
        cte_type=CompileSqlScenarioCte,
        syntax=syntax,
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
    *, ctes: tuple[CompileSqlScenarioCte, ...], file_label: str, syntax: SqlLexicalSyntax
) -> CompileSqlScenarioCtes:
    validate_independent_expected_and_assertion_ctes(
        ctes=ctes,
        expected_prefix=EXPECTED_TEST_CTE_PREFIX,
        assertion_prefix=ASSERT_SCENARIO_CTE_PREFIX,
        file_label=file_label,
        context_label="SQL scenario",
        syntax=syntax,
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
