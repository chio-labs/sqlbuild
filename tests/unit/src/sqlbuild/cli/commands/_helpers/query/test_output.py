from __future__ import annotations

import pytest

from sqlbuild._native import render_query_result
from sqlbuild.adapter.contract.models import QueryResult
from tests.unit.src.sqlbuild.cli.commands._helpers.query._test_types import (
    QueryOutputTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        QueryOutputTestCase(
            description="renders non row returning statements as ok",
            result=QueryResult(),
            output_format="long",
            limit=20,
            expected_output="OK\n",
        ),
        QueryOutputTestCase(
            description="renders long output by default shape",
            result=QueryResult(
                columns=("id", "name"),
                rows=((1, "alice"), (2, None)),
            ),
            output_format="long",
            limit=20,
            expected_output=(
                "-[ RECORD 1 ]---------------------------+\n"
                "id   | 1\n"
                "name | alice\n"
                "\n"
                "-[ RECORD 2 ]---------------------------+\n"
                "id   | 2\n"
                "name | NULL\n"
                "\n"
                "2 rows\n"
            ),
        ),
        QueryOutputTestCase(
            description="renders truncated message when limited",
            result=QueryResult(columns=("id",), rows=((1,),), truncated=True),
            output_format="long",
            limit=1,
            expected_output=(
                "-[ RECORD 1 ]---------------------------+\n"
                "id | 1\n"
                "\n"
                "1 row shown (limit 1; use --limit or --no-limit)\n"
            ),
        ),
        QueryOutputTestCase(
            description="renders json rows",
            result=QueryResult(columns=("id", "name"), rows=((1, "alice"),)),
            output_format="json",
            limit=20,
            expected_output='[{"id": 1, "name": "alice"}]\n',
        ),
        QueryOutputTestCase(
            description="leaves a type cell empty where the adapter reports no type",
            result=QueryResult(
                columns=("order_id", "status"),
                rows=((7, "open"),),
                column_types=("INTEGER", None),
            ),
            output_format=None,
            limit=20,
            expected_output=(
                "┌──────────┬────────┐\n"
                "│ order_id │ status │\n"
                "│ INTEGER  │        │\n"
                "├──────────┼────────┤\n"
                "│        7 │ open   │\n"
                "└──────────┴────────┘\n"
                "\n"
                "1 row\n"
            ),
        ),
        QueryOutputTestCase(
            description="renders a box with the warehouse types when the result fits",
            result=QueryResult(
                columns=("order_id", "amount"),
                rows=((7, "12.50"),),
                column_types=("INTEGER", "DECIMAL(10,2)"),
            ),
            output_format=None,
            limit=20,
            expected_output=(
                "┌──────────┬───────────────┐\n"
                "│ order_id │    amount     │\n"
                "│ INTEGER  │ DECIMAL(10,2) │\n"
                "├──────────┼───────────────┤\n"
                "│        7 │ 12.50         │\n"
                "└──────────┴───────────────┘\n"
                "\n"
                "1 row\n"
            ),
        ),
        QueryOutputTestCase(
            description="renders records when a value spans lines, so nothing is cut",
            result=QueryResult(columns=("note",), rows=(("first\nsecond",),)),
            output_format=None,
            limit=20,
            expected_output=(
                "-[ RECORD 1 ]---------------------------+\nnote | first\nsecond\n\n1 row\n"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_query_result_when_rendering_then_returns_expected_output(
    test_case: QueryOutputTestCase,
) -> None:
    result: str = render_query_result(
        result=test_case.result,
        output_format=test_case.output_format,
        limit=test_case.limit,
    )

    assert result == test_case.expected_output
