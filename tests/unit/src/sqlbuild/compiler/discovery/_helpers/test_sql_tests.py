from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.sql.tests import parse_sql_test_file
from sqlbuild.compiler.discovery.exceptions import SqlTestParseError
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestCase,
    SqlTestParameterDeclaration,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    ParseSqlTestFileErrorTestCase,
    ParseSqlTestFileTestCase,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers.helpers import (
    discovered_test_case_values,
    discovered_test_cases,
    discovered_test_parameters,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParseSqlTestFileTestCase(
            description="discovers one unnamed test block",
            contents="""
        TEST ();

        WITH
        __source__orders AS (
          SELECT 1 AS order_id
        )
        SELECT 1
        """,
            expected_names=(None,),
            expected_sql_bodies=(
                "WITH\n__source__orders AS (\n  SELECT 1 AS order_id\n)\nSELECT 1",
            ),
            expected_test_indexes=(1,),
            expected_header_values=({},),
        ),
        ParseSqlTestFileTestCase(
            description="discovers multiple named test blocks from one file",
            contents="""
        TEST (name "first");

        WITH
        __source__orders AS (
          SELECT 1 AS order_id
        )
        SELECT 1;

        TEST (name "second");

        WITH
        __ref__orders AS (
          SELECT 2 AS order_id
        )
        SELECT 1
        """,
            expected_names=("first", "second"),
            expected_sql_bodies=(
                "WITH\n__source__orders AS (\n  SELECT 1 AS order_id\n)\nSELECT 1;",
                "WITH\n__ref__orders AS (\n  SELECT 2 AS order_id\n)\nSELECT 1",
            ),
            expected_test_indexes=(1, 2),
            expected_header_values=({"name": "first"}, {"name": "second"}),
        ),
        ParseSqlTestFileTestCase(
            description="parses a single named test block",
            contents="""
        TEST (name "orders logic", mode macro);

        SELECT 1
        """,
            expected_names=("orders logic",),
            expected_sql_bodies=("SELECT 1",),
            expected_test_indexes=(1,),
            expected_header_values=({"name": "orders logic", "mode": "macro"},),
        ),
        ParseSqlTestFileTestCase(
            description="parses typed ordered cases with nullable values",
            contents="""
        TEST (
          name "typed values",
          parameters (
            text_value string,
            integer_value integer,
            boolean_value boolean,
            float_value float,
            decimal_value decimal,
            optional_value (type string, nullable true),
          ),
          cases (
            first (
              text_value "O\\'Brien",
              integer_value -7,
              boolean_value true,
              float_value 1.25,
              decimal_value "2.4700",
              optional_value null,
            ),
            second (
              text_value "open",
              integer_value 8,
              boolean_value false,
              float_value -0.5,
              decimal_value "3.00",
              optional_value "present",
            ),
          ),
        );

        SELECT @param("text_value")
        """,
            expected_names=("typed values",),
            expected_sql_bodies=('SELECT @param("text_value")',),
            expected_test_indexes=(1,),
            expected_header_values=(
                {
                    "name": "typed values",
                    "parameters": {
                        "text_value": "string",
                        "integer_value": "integer",
                        "boolean_value": "boolean",
                        "float_value": "float",
                        "decimal_value": "decimal",
                        "optional_value": {"type": "string", "nullable": True},
                    },
                    "cases": {
                        "first": {
                            "text_value": "O'Brien",
                            "integer_value": -7,
                            "boolean_value": True,
                            "float_value": 1.25,
                            "decimal_value": "2.4700",
                            "optional_value": None,
                        },
                        "second": {
                            "text_value": "open",
                            "integer_value": 8,
                            "boolean_value": False,
                            "float_value": -0.5,
                            "decimal_value": "3.00",
                            "optional_value": "present",
                        },
                    },
                },
            ),
            expected_parameter_types=(
                "string",
                "integer",
                "boolean",
                "float",
                "decimal",
                "string",
            ),
            expected_parameter_nullability=(False, False, False, False, False, True),
            expected_case_names=("first", "second"),
            expected_case_values=(
                ("O'Brien", -7, True, 1.25, Decimal("2.4700"), None),
                ("open", 8, False, -0.5, Decimal("3.00"), "present"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_test_file_variants_when_parsing_then_it_returns_expected_raw_blocks(
    test_case: ParseSqlTestFileTestCase,
) -> None:
    discovered_blocks: tuple[DiscoveredSqlTestBlock, ...] = parse_sql_test_file(
        contents=test_case.contents, file_path=Path("tests/unit/orders.sql")
    )

    assert tuple(block.name for block in discovered_blocks) == test_case.expected_names
    assert tuple(block.sql_body for block in discovered_blocks) == test_case.expected_sql_bodies
    assert tuple(block.test_index for block in discovered_blocks) == test_case.expected_test_indexes
    assert tuple(block.header_values for block in discovered_blocks) == (
        test_case.expected_header_values
    )
    parameters: tuple[SqlTestParameterDeclaration, ...] = discovered_test_parameters(
        blocks=discovered_blocks
    )
    cases: tuple[DiscoveredSqlTestCase, ...] = discovered_test_cases(blocks=discovered_blocks)
    assert tuple(parameter.value_type.value for parameter in parameters) == (
        test_case.expected_parameter_types
    )
    assert tuple(parameter.nullable for parameter in parameters) == (
        test_case.expected_parameter_nullability
    )
    assert tuple(case.name for case in cases) == test_case.expected_case_names
    assert tuple(case.case_index for case in cases) == tuple(range(len(cases)))
    assert discovered_test_case_values(cases=cases) == test_case.expected_case_values


@pytest.mark.parametrize(
    "test_case",
    [
        ParseSqlTestFileErrorTestCase(
            description="raises when the file does not start with a test header",
            contents="SELECT 1\n",
            expected_error_fragment="must start with a TEST",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when leading comments appear before the first test header",
            contents="-- comment\nTEST ();\n\nSELECT 1\n",
            expected_error_fragment="must start with a TEST",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a test block has no sql body",
            contents="TEST ();\n",
            expected_error_fragment="must define SQL after TEST(...)",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects the old colon syntax",
            contents="""
        TEST (name: "orders");

        SELECT 1
        """,
            expected_error_fragment="unexpected ':' after key 'name'",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the test header includes unsupported keys",
            contents="""
        TEST (name "orders", chain true);

        SELECT 1
        """,
            expected_error_fragment="unsupported keys: chain",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the test name is blank",
            contents="""
        TEST (name "   ");

        SELECT 1
        """,
            expected_error_fragment="must be a non-empty string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the test name is not a string",
            contents="""
        TEST (name 123);

        SELECT 1
        """,
            expected_error_fragment="must be a non-empty string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects an explicit null test name",
            contents="TEST (name null);\n\nSELECT 1\n",
            expected_error_fragment="name.*must be a non-empty string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects an explicit null test mode with a discovery error",
            contents="TEST (mode null);\n\nSELECT 1\n",
            expected_error_fragment="mode.*must be a string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a multi-block file leaves one block unnamed",
            contents="""
        TEST (name "first");

        SELECT 1;

        TEST ();

        SELECT 1
        """,
            expected_error_fragment="every block must define a unique `name`",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a multi-block file repeats a test name",
            contents="""
        TEST (name "shared");

        SELECT 1;

        TEST (name "shared");

        SELECT 1
        """,
            expected_error_fragment=r"defines duplicate TEST\(\) name 'shared'",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects duplicate header keys",
            contents='TEST (name "first", name "second");\n\nSELECT 1\n',
            expected_error_fragment="duplicate.*name",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects an unknown test mode",
            contents="TEST (mode integration);\n\nSELECT 1\n",
            expected_error_fragment="mode.*must be one of",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects parameters without cases",
            contents="TEST (parameters (status string));\n\nSELECT 1\n",
            expected_error_fragment="must define `parameters` and `cases` together",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects duplicate parameter names",
            contents=(
                "TEST (parameters (status string, status string), "
                'cases (one (status "open")));\nSELECT 1\n'
            ),
            expected_error_fragment="duplicate key 'status'",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects duplicate case names",
            contents=(
                "TEST (parameters (status string), cases ("
                'one (status "open"), one (status "closed")));\nSELECT 1\n'
            ),
            expected_error_fragment="duplicate key 'one'",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects missing case parameters",
            contents=(
                "TEST (parameters (status string, expected string), "
                'cases (one (status "open")));\nSELECT 1\n'
            ),
            expected_error_fragment="missing parameters: expected",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects undeclared case parameters",
            contents=(
                "TEST (parameters (status string), "
                'cases (one (status "open", expected "open")));\nSELECT 1\n'
            ),
            expected_error_fragment="undeclared parameters: expected",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects incompatible typed values",
            contents=('TEST (parameters (count integer), cases (one (count "1")));\nSELECT 1\n'),
            expected_error_fragment="has type str; expected integer",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects null for non-nullable parameters",
            contents="TEST (parameters (status string), cases (one (status null)));\nSELECT 1\n",
            expected_error_fragment="is not nullable",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects malformed case names",
            contents=(
                "TEST (parameters (status string), "
                'cases ("not valid" (status "open")));\nSELECT 1\n'
            ),
            expected_error_fragment="expected key",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_test_file_contents_when_parsing_then_it_raises_clear_errors(
    test_case: ParseSqlTestFileErrorTestCase,
) -> None:
    with pytest.raises(SqlTestParseError, match=test_case.expected_error_fragment):
        parse_sql_test_file(contents=test_case.contents, file_path=Path("tests/unit/orders.sql"))
