from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.sql.tests import parse_sql_test_file
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    ParseSqlTestFileErrorTestCase,
    ParseSqlTestFileTestCase,
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
        ),
        ParseSqlTestFileTestCase(
            description="discovers multiple named test blocks from one file",
            contents="""
        TEST (name: "first");

        WITH
        __source__orders AS (
          SELECT 1 AS order_id
        )
        SELECT 1;

        TEST (name: "second");

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
        ),
        ParseSqlTestFileTestCase(
            description="parses a single named test block",
            contents="""
        TEST (name: "orders logic");

        SELECT 1
        """,
            expected_names=("orders logic",),
            expected_sql_bodies=("SELECT 1",),
            expected_test_indexes=(1,),
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
            description="raises when the test header contains malformed yaml",
            contents="""
        TEST (name: [broken);

        SELECT 1
        """,
            expected_error_fragment="could not be parsed",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the test header includes unsupported keys",
            contents="""
        TEST (name: "orders", chain: true);

        SELECT 1
        """,
            expected_error_fragment="only supports `name` and `mode`; unsupported keys: chain",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the test name is blank",
            contents="""
        TEST (name: "   ");

        SELECT 1
        """,
            expected_error_fragment="must be a non-empty string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the test name is not a string",
            contents="""
        TEST (name: 123);

        SELECT 1
        """,
            expected_error_fragment="must be a non-empty string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a multi-block file leaves one block unnamed",
            contents="""
        TEST (name: "first");

        SELECT 1;

        TEST ();

        SELECT 1
        """,
            expected_error_fragment="every block must define a unique `name`",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a multi-block file repeats a test name",
            contents="""
        TEST (name: "shared");

        SELECT 1;

        TEST (name: "shared");

        SELECT 1
        """,
            expected_error_fragment=r"defines duplicate TEST\(\) name 'shared'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_test_file_contents_when_parsing_then_it_raises_clear_errors(
    test_case: ParseSqlTestFileErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        parse_sql_test_file(contents=test_case.contents, file_path=Path("tests/unit/orders.sql"))
