"""Tests for supported keys in SQL FUNCTION headers and Python @udf decorators."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.python.functions import parse_python_function
from sqlbuild.compiler.discovery._helpers.sql.functions import parse_function_sql
from sqlbuild.compiler.discovery.exceptions import ModelSqlParseError
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    FunctionHeaderKeysTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FunctionHeaderKeysTestCase(
            description="sql udf with every supported key",
            file_name="normalize_status.sql",
            contents=(
                "FUNCTION (\n  arguments (status VARCHAR),\n  returns VARCHAR,\n"
                "  database analytics,\n  schema udfs,\n  tags [orders],\n);\n\nlower(status)\n"
            ),
            expected_keys=("arguments", "database", "returns", "schema", "tags"),
        ),
        FunctionHeaderKeysTestCase(
            description="table function with a returns table declaration",
            file_name="expand_order.sql",
            contents=(
                "FUNCTION (\n  arguments (order_id INTEGER),\n"
                "  returns table (order_id INTEGER),\n);\n\nSELECT order_id\n"
            ),
            expected_keys=("arguments", "returns"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_function_header_keys_when_parsing_then_accepts_header(
    test_case: FunctionHeaderKeysTestCase,
) -> None:
    header_values: dict[str, object]
    header_values, _ = parse_function_sql(
        contents=test_case.contents, file_path=Path(test_case.file_name)
    )

    assert tuple(sorted(header_values)) == test_case.expected_keys


@pytest.mark.parametrize(
    "test_case",
    [
        FunctionHeaderKeysTestCase(
            description="sql udf with a replay setting",
            file_name="normalize_status.sql",
            contents=(
                "FUNCTION (\n  arguments (status VARCHAR),\n  returns VARCHAR,\n"
                "  replay_on_change full,\n);\n\nlower(status)\n"
            ),
            expected_error=(
                "FUNCTION() in 'normalize_status.sql:4' has unsupported keys: replay_on_change"
            ),
        ),
        FunctionHeaderKeysTestCase(
            description="table function with two unknown keys",
            file_name="expand_order.sql",
            contents=(
                'FUNCTION (\n  description "Expand one order",\n  arguments (order_id INTEGER),\n'
                "  returns table (order_id INTEGER),\n  owner orders_team,\n);\n\nSELECT order_id\n"
            ),
            expected_error=(
                "FUNCTION() in 'expand_order.sql:2' has unsupported keys: description, owner"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_sql_function_header_key_when_parsing_then_rejects_key_with_location(
    test_case: FunctionHeaderKeysTestCase,
) -> None:
    with pytest.raises(ModelSqlParseError) as raised:
        parse_function_sql(contents=test_case.contents, file_path=Path(test_case.file_name))

    assert raised.value.message == test_case.expected_error
    assert raised.value.code == "D002"


@pytest.mark.parametrize(
    "test_case",
    [
        FunctionHeaderKeysTestCase(
            description="python udf with a replay setting",
            file_name="normalize_status_py.py",
            contents=(
                "from sqlbuild.functions import udf\n\n\n@udf(\n"
                '    arguments={"status": "VARCHAR"},\n    returns="VARCHAR",\n'
                '    replay_on_change="full",\n)\ndef main(status):\n    return status\n'
            ),
            expected_error=(
                "@udf(...) in 'normalize_status_py.py:7' has unsupported keys: replay_on_change"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_python_udf_key_when_parsing_then_rejects_key_with_location(
    test_case: FunctionHeaderKeysTestCase,
) -> None:
    with pytest.raises(ModelSqlParseError) as raised:
        parse_python_function(contents=test_case.contents, file_path=Path(test_case.file_name))

    assert raised.value.message == test_case.expected_error


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
