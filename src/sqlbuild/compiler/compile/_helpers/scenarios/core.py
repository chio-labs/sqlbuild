"""SQL-native scenario compile-semantic extraction helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.sql_tests.core import scanned_expected_model_names
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def extract_sql_scenario_expected_model_names(
    *, sql: str, file_label: str, syntax: SqlLexicalSyntax
) -> tuple[str, ...]:
    """Extract explicit expected-model relationships without inspecting CTE bodies."""

    return scanned_expected_model_names(
        sql=sql, file_label=file_label, scenario=True, syntax=syntax
    )
