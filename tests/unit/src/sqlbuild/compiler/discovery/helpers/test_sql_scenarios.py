from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.sql.scenarios import parse_sql_scenario_file
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    ParseSqlScenarioFileErrorTestCase,
    ParseSqlScenarioFileTestCase,
)

TEST_CASES: list[ParseSqlScenarioFileTestCase] = [
    ParseSqlScenarioFileTestCase(
        description="parses scenario metadata and sql body",
        contents="""
        SCENARIO (description: "Customer refund case", tags: ["revenue", "refunds"]);

        WITH
        __source__raw__orders AS (
          SELECT 1 AS order_id
        ),
        __expected__daily_revenue AS (
          SELECT 1 AS order_id
        )
        SELECT 1
        """,
        expected_name="revenue__customer_refund",
        expected_header_values={
            "description": "Customer refund case",
            "tags": ["revenue", "refunds"],
        },
        expected_sql_body=(
            "WITH\n"
            "__source__raw__orders AS (\n"
            "  SELECT 1 AS order_id\n"
            "),\n"
            "__expected__daily_revenue AS (\n"
            "  SELECT 1 AS order_id\n"
            ")\n"
            "SELECT 1"
        ),
    ),
    ParseSqlScenarioFileTestCase(
        description="parses empty scenario header",
        contents="""
        SCENARIO ();

        WITH
        __assert__daily_revenue_has_rows AS (
          SELECT * FROM __ref(daily_revenue) WHERE order_id IS NULL
        )
        SELECT 1
        """,
        expected_name="revenue__customer_refund",
        expected_header_values={},
        expected_sql_body=(
            "WITH\n"
            "__assert__daily_revenue_has_rows AS (\n"
            "  SELECT * FROM __ref(daily_revenue) WHERE order_id IS NULL\n"
            ")\n"
            "SELECT 1"
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_sql_scenario_file_variants_when_parsing_then_it_returns_expected_scenario(
    test_case: ParseSqlScenarioFileTestCase,
) -> None:
    discovered_scenario: DiscoveredSqlScenarioFile = parse_sql_scenario_file(
        contents=test_case.contents,
        file_path=Path("tests/scenarios/revenue/revenue__customer_refund.sql"),
        relative_path=Path("tests/scenarios/revenue/revenue__customer_refund.sql"),
    )

    assert discovered_scenario.name == test_case.expected_name
    assert discovered_scenario.header_values == test_case.expected_header_values
    assert discovered_scenario.sql_body == test_case.expected_sql_body


ERROR_TEST_CASES: list[ParseSqlScenarioFileErrorTestCase] = [
    ParseSqlScenarioFileErrorTestCase(
        description="raises when file does not start with scenario header",
        contents="SELECT 1\n",
        expected_error_fragment="must start with a SCENARIO",
    ),
    ParseSqlScenarioFileErrorTestCase(
        description="raises when scenario header includes unsupported name",
        contents="""
        SCENARIO (name: "customer_refund");

        SELECT 1
        """,
        expected_error_fragment="only supports `description` and `tags`",
    ),
    ParseSqlScenarioFileErrorTestCase(
        description="raises when description is not a string",
        contents="""
        SCENARIO (description: 123);

        SELECT 1
        """,
        expected_error_fragment="description.*must be a string",
    ),
    ParseSqlScenarioFileErrorTestCase(
        description="raises when tags is not a list of strings",
        contents="""
        SCENARIO (tags: [revenue, 123]);

        SELECT 1
        """,
        expected_error_fragment="tags.*must be a list of strings",
    ),
    ParseSqlScenarioFileErrorTestCase(
        description="raises when scenario has no sql body",
        contents="SCENARIO ();\n",
        expected_error_fragment="must define SQL after SCENARIO",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_sql_scenario_file_contents_when_parsing_then_it_raises_clear_errors(
    test_case: ParseSqlScenarioFileErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        parse_sql_scenario_file(
            contents=test_case.contents,
            file_path=Path("tests/scenarios/revenue/revenue__customer_refund.sql"),
            relative_path=Path("tests/scenarios/revenue/revenue__customer_refund.sql"),
        )
