from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.sql.audits import parse_sql_audit_file
from sqlbuild.compiler.discovery.models import DiscoveredAuditBlock
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    ParseSqlAuditFileErrorTestCase,
    ParseSqlAuditFileTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
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
        ParseSqlAuditFileTestCase(
            description="parses a single named audit block",
            contents="""
        AUDIT (name: "negative totals");

        SELECT 1
        """,
            expected_names=("negative totals",),
            expected_sql_bodies=("SELECT 1",),
            expected_audit_indexes=(1,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_audit_file_variants_when_parsing_then_it_returns_expected_raw_blocks(
    test_case: ParseSqlAuditFileTestCase,
) -> None:
    discovered_blocks: tuple[DiscoveredAuditBlock, ...] = parse_sql_audit_file(
        contents=test_case.contents, file_path=Path("audits/orders.sql")
    )

    assert tuple(block.name for block in discovered_blocks) == test_case.expected_names
    assert tuple(block.sql_body for block in discovered_blocks) == test_case.expected_sql_bodies
    assert (
        tuple(block.audit_index for block in discovered_blocks) == test_case.expected_audit_indexes
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ParseSqlAuditFileErrorTestCase(
            description="raises when the file does not start with an audit header",
            contents="SELECT 1\n",
            expected_error_fragment="must start with an AUDIT",
        ),
        ParseSqlAuditFileErrorTestCase(
            description="raises when leading comments appear before the first audit header",
            contents="-- comment\nAUDIT ();\n\nSELECT 1\n",
            expected_error_fragment="must start with an AUDIT",
        ),
        ParseSqlAuditFileErrorTestCase(
            description="raises when an audit block has no sql body",
            contents="AUDIT ();\n",
            expected_error_fragment="must define SQL after AUDIT(...)",
        ),
        ParseSqlAuditFileErrorTestCase(
            description="raises when the audit header contains malformed yaml",
            contents="""
        AUDIT (name: [broken);

        SELECT 1
        """,
            expected_error_fragment="could not be parsed",
        ),
        ParseSqlAuditFileErrorTestCase(
            description="raises when the audit header includes unsupported keys",
            contents="""
        AUDIT (name: "negative totals", unsupported: true);

        SELECT 1
        """,
            expected_error_fragment="unsupported keys: unsupported",
        ),
        ParseSqlAuditFileErrorTestCase(
            description="raises when the audit name is blank",
            contents="""
        AUDIT (name: "   ");

        SELECT 1
        """,
            expected_error_fragment="must be a non-empty string",
        ),
        ParseSqlAuditFileErrorTestCase(
            description="raises when the audit name is not a string",
            contents="""
        AUDIT (name: 123);

        SELECT 1
        """,
            expected_error_fragment="must be a non-empty string",
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
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_audit_file_contents_when_parsing_then_it_raises_clear_errors(
    test_case: ParseSqlAuditFileErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        parse_sql_audit_file(contents=test_case.contents, file_path=Path("audits/orders.sql"))
