from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.models import QueryResult
from sqlbuild.cli.commands._helpers.query.output import render_query_result
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
                "1 row\n"
                "Showing 1 rows. Use --limit to show more or --no-limit to disable the limit.\n"
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
            description="renders csv rows",
            result=QueryResult(columns=("id", "name"), rows=((1, "alice"),)),
            output_format="csv",
            limit=20,
            expected_output="id,name\n1,alice\n",
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
