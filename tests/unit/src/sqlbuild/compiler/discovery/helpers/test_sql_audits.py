from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.sql_audits import parse_sql_audit_file
from sqlbuild.compiler.discovery.models import DiscoveredAuditBlock
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    ParseSqlAuditFileErrorTestCase,
    ParseSqlAuditFileTestCase,
)

TEST_CASES: list[ParseSqlAuditFileTestCase] = [
    ParseSqlAuditFileTestCase(
        description="discovers one unnamed audit block",
        contents="""
        AUDIT ();

        SELECT order_id
        FROM __ref("orders")
        WHERE order_total < 0
        """,
        expected_names=(None,),
        expected_sql_bodies=('SELECT order_id\nFROM __ref("orders")\nWHERE order_total < 0',),
        expected_audit_indexes=(1,),
    ),
    ParseSqlAuditFileTestCase(
        description="discovers multiple named audit blocks from one file",
        contents="""
        AUDIT (name: "negative totals");

        SELECT order_id
        FROM __ref("orders")
        WHERE order_total < 0;

        AUDIT (name: "missing customers");

        SELECT customer_id
        FROM __ref("orders")
        WHERE customer_id IS NULL
        """,
        expected_names=("negative totals", "missing customers"),
        expected_sql_bodies=(
            'SELECT order_id\nFROM __ref("orders")\nWHERE order_total < 0;',
            'SELECT customer_id\nFROM __ref("orders")\nWHERE customer_id IS NULL',
        ),
        expected_audit_indexes=(1, 2),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_sql_audit_file_variants_when_parsing_then_it_returns_expected_raw_blocks(
    test_case: ParseSqlAuditFileTestCase,
) -> None:
    discovered_blocks: tuple[DiscoveredAuditBlock, ...] = parse_sql_audit_file(
        test_case.contents, Path("audits/orders.sql")
    )

    assert tuple(block.name for block in discovered_blocks) == test_case.expected_names
    assert tuple(block.sql_body for block in discovered_blocks) == test_case.expected_sql_bodies
    assert (
        tuple(block.audit_index for block in discovered_blocks) == test_case.expected_audit_indexes
    )


ERROR_TEST_CASES: list[ParseSqlAuditFileErrorTestCase] = [
    ParseSqlAuditFileErrorTestCase(
        description="raises when the file does not start with an audit header",
        contents="SELECT 1\n",
        expected_error_fragment="must start with an AUDIT",
    ),
    ParseSqlAuditFileErrorTestCase(
        description="raises when a multi-block file leaves one audit unnamed",
        contents="""
        AUDIT (name: "negative totals");

        SELECT 1;

        AUDIT ();

        SELECT 1
        """,
        expected_error_fragment="every block must define a unique `name`",
    ),
    ParseSqlAuditFileErrorTestCase(
        description="raises when a multi-block file repeats an audit name",
        contents="""
        AUDIT (name: "shared");

        SELECT 1;

        AUDIT (name: "shared");

        SELECT 1
        """,
        expected_error_fragment=r"defines duplicate AUDIT\(\) name 'shared'",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_sql_audit_file_contents_when_parsing_then_it_raises_clear_errors(
    test_case: ParseSqlAuditFileErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        parse_sql_audit_file(test_case.contents, Path("audits/orders.sql"))
