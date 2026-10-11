"""SQL-test declaration usages come from the native reference scan and match Python's walk."""

from __future__ import annotations

import pytest

from tests.integration.src.sqlbuild.compiler.compile._test_types import DeclarationUsageTestCase
from tests.integration.src.sqlbuild.compiler.compile.helpers import declaration_usage_outcome
from tests.integration.src.sqlbuild.compiler.helpers import (
    GoldenEntry,
    golden_differences,
    golden_entry,
    golden_name,
    read_golden,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationUsageTestCase(
            description="usage scan edges",
            texts=(
                "SELECT @enum('status').OPEN, @const('rate')",
                "SELECT @enum('status') , @const('rate')",
                "SELECT @enum x 'unclosed",
                "SELECT @enum x, @const('rate') 'unclosed",
                'SELECT @const(rate), @enum("size").S',
                "SELECT '@enum(''status'').A', @const('rate') /* open",
                "SELECT @enumx('status').A, @const_x('rate'), @consté, @const('rate')",
                "SELECT $$ @enum('status').A $$, @enum('size').M -- @const('rate')\n",
                "SELECT x$$ @const('rate') $$",
                "SELECT @enum ( 'status' ) . OPEN, @enum('status').OPEN, @const('missing')",
                "SELECT `@const('rate')`, \"@enum('size').A\"",
                "SELECT @const('rate'), @const('rate'), 'é' @enum('size').XL",
                "SELECT @@const, @enum, @const",
                "SELECT 1",
                "SELECT @enum('status').OPEN /* @const('rate') */ 'it''s' @const('rate')",
                "SELECT @const('rate' ",
                "SELECT /* x @const('rate')",
                "SELECT 'a @enum('status').A",
                "SELECT @enum x 'oops @const('rate')",
                "SELECT @const('rate') $tag$ @enum('size').S",
                "SELECT @enum(\"status\").OPEN, @const('rate') /* tail @enum('size').S",
            ),
            expected_differences=[],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_declaration_references_when_collecting_usages_then_matches_python_golden(
    test_case: DeclarationUsageTestCase,
) -> None:
    outcomes: list[tuple[object, ...]] = [declaration_usage_outcome(sql) for sql in test_case.texts]
    expected: list[GoldenEntry] = read_golden(
        golden_name("declaration_usages", test_case.description)
    )

    assert (
        golden_differences(
            expected, [golden_entry("declaration_usages", outcome) for outcome in outcomes]
        )
        == test_case.expected_differences
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
