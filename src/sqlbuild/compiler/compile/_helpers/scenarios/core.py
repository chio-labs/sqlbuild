"""SQL-native scenario compile-semantic extraction helpers."""

from __future__ import annotations

from typing import Any

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.sql_tests.core import scanned_expected_model_names
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlScenarioCte,
    CompileSqlScenarioCtes,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def extract_sql_scenario_ctes(
    *, sql: str, file_label: str, syntax: SqlLexicalSyntax
) -> CompileSqlScenarioCtes:
    """Extract top-level SQL-native scenario fixture, expected, and assertion CTEs."""

    outcome: dict[str, Any] = orjson.loads(
        _native.extract_sql_scenario_json(sql, file_label, syntax.native_mapping)
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

    return scanned_expected_model_names(
        sql=sql, file_label=file_label, scenario=True, syntax=syntax
    )
