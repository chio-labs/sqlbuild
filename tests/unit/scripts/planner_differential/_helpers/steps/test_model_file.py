"""Model-file edits split the MODEL header from a single query and insert properties."""

from __future__ import annotations

import pytest

from scripts.planner_differential._helpers.steps.model_file import (
    add_header_property,
    join_model_file,
    split_model_file,
)
from scripts.planner_differential.models import ModelFile
from tests.unit.scripts.planner_differential._helpers.steps._test_types import (
    HeaderPropertyTestCase,
    JoinModelFileTestCase,
    SplitModelFileTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SplitModelFileTestCase(
            description="multi_line_header",
            text="MODEL (\n  materialized table,\n  columns (id (nullable false)),\n);\n\n"
            'SELECT id FROM __ref("orders");\n',
            expected_model_file=ModelFile(
                header="MODEL (\n  materialized table,\n  columns (id (nullable false)),\n);",
                query='SELECT id FROM __ref("orders")',
            ),
        ),
        SplitModelFileTestCase(
            description="inline_header",
            text="MODEL (materialized view);\nSELECT 1 AS id\n",
            expected_model_file=ModelFile(
                header="MODEL (materialized view);", query="SELECT 1 AS id"
            ),
        ),
        SplitModelFileTestCase(
            description="no_header",
            text="SELECT 1 AS id\n",
            expected_model_file=ModelFile(header="", query="SELECT 1 AS id"),
        ),
        SplitModelFileTestCase(
            description="several_statements_are_not_edited",
            text="MODEL (\n  materialized table,\n);\n\nSET x = 1;\nSELECT 1 AS id\n",
            expected_model_file=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_file_when_splitting_then_header_and_query_are_separated(
    test_case: SplitModelFileTestCase,
) -> None:
    assert split_model_file(test_case.text) == test_case.expected_model_file


@pytest.mark.parametrize(
    "test_case",
    [
        HeaderPropertyTestCase(
            description="existing_header",
            header="MODEL (\n  materialized table,\n);",
            line="tags [orders],",
            expected_header="MODEL (\n  tags [orders],\n  materialized table,\n);",
        ),
        HeaderPropertyTestCase(
            description="no_header",
            header="",
            line="tags [orders],",
            expected_header="MODEL (\n  tags [orders],\n);",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_header_when_adding_property_then_it_leads_the_header(
    test_case: HeaderPropertyTestCase,
) -> None:
    assert (
        add_header_property(header=test_case.header, line=test_case.line)
        == test_case.expected_header
    )


@pytest.mark.parametrize(
    "test_case",
    [
        JoinModelFileTestCase(
            description="header_and_query",
            model_file=ModelFile(header="MODEL (\n  materialized view,\n);", query="SELECT 1"),
            expected_text="MODEL (\n  materialized view,\n);\n\nSELECT 1\n",
        ),
        JoinModelFileTestCase(
            description="query_only",
            model_file=ModelFile(header="", query="SELECT 1"),
            expected_text="SELECT 1\n",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_split_file_when_joining_then_header_and_query_are_separated(
    test_case: JoinModelFileTestCase,
) -> None:
    assert join_model_file(test_case.model_file) == test_case.expected_text


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
