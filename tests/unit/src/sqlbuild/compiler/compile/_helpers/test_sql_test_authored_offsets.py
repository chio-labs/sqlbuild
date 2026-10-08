"""Offsets in a discovered SQL test body map back to the exact authored file position."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile._helpers.sql_tests.extraction_errors import authored_file_offset
from sqlbuild.compiler.discovery.main._parse_sql_test_file import parse_sql_test_file
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock, DiscoveredSqlTestFile
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import AuthoredOffsetTestCase

_PATH: Path = Path("tests/unit/orders.sql")


@pytest.mark.parametrize(
    "test_case",
    [
        AuthoredOffsetTestCase(
            description="flush-left body after a comment that repeats the marker",
            contents="TEST ();\n-- zz_mark is named here\nWITH\nzz_mark AS (SELECT 1 AS a)\n",
            marker="zz_mark AS",
            expected_line_column=(4, 1),
        ),
        AuthoredOffsetTestCase(
            description="indented body with a tab before the marker",
            contents="TEST ();\n    WITH\n    h AS (SELECT 1 AS a),\n    \tzz_mark AS (SELECT 1)\n",
            marker="zz_mark",
            expected_line_column=(4, 6),
        ),
        AuthoredOffsetTestCase(
            description="tab inside a line before the marker",
            contents="TEST ();\nWITH\nh AS (SELECT 1\t AS a, 'é' AS zz_mark)\n",
            marker="zz_mark",
            expected_line_column=(3, 30),
        ),
        AuthoredOffsetTestCase(
            description="second block with blank lines after its header",
            contents=(
                'TEST (name "one");\nWITH a AS (SELECT 1)\n;\nTEST (name "two");\n\n\n'
                "  WITH\n  b AS (SELECT zz_mark)\n"
            ),
            marker="zz_mark",
            expected_line_column=(8, 16),
        ),
        AuthoredOffsetTestCase(
            description="first body line indented on the header line",
            contents="TEST ();   WITH zz_mark AS (SELECT 1)\n  , b AS (SELECT 2)\n",
            marker="zz_mark",
            expected_line_column=(1, 17),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_discovered_block_when_mapping_body_offset_then_points_at_authored_text(
    test_case: AuthoredOffsetTestCase,
) -> None:
    blocks: tuple[DiscoveredSqlTestBlock, ...] = parse_sql_test_file(
        contents=test_case.contents, file_path=_PATH
    )
    test_block: DiscoveredSqlTestBlock = blocks[-1]
    test_file: DiscoveredSqlTestFile = DiscoveredSqlTestFile(
        file_path=_PATH, relative_path=_PATH, contents=test_case.contents, blocks=blocks
    )
    body_offset: int = test_block.sql_body.rindex(test_case.marker)

    offset: int | None = authored_file_offset(
        test_file=test_file, test_block=test_block, body_offset=body_offset
    )

    contents: str = test_case.contents
    resolved: int = offset or 0
    assert (
        contents[resolved : resolved + len(test_case.marker)],
        contents.count("\n", 0, resolved) + 1,
        resolved - contents.rfind("\n", 0, resolved),
    ) == (test_case.marker, *test_case.expected_line_column)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
