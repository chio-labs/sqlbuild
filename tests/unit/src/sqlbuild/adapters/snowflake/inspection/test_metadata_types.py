"""SHOW COLUMNS type metadata must render exactly the INFORMATION_SCHEMA type strings."""

from __future__ import annotations

import json

import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.snowflake._helpers.metadata_types import (
    information_schema_type,
    show_columns_type,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection._test_types import (
    InvalidShowColumnTypeTestCase,
    ShowColumnTypeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ShowColumnTypeTestCase(
            description="integer number",
            show_data_type={"type": "FIXED", "precision": 38, "scale": 0, "nullable": True},
            information_schema_fields=("NUMBER", 38, 0, None),
            expected_type="NUMBER(38,0)",
        ),
        ShowColumnTypeTestCase(
            description="decimal number",
            show_data_type={"type": "FIXED", "precision": 10, "scale": 2, "nullable": False},
            information_schema_fields=("NUMBER", 10, 2, None),
            expected_type="NUMBER(10,2)",
        ),
        ShowColumnTypeTestCase(
            description="float",
            show_data_type={"type": "REAL", "nullable": True},
            information_schema_fields=("FLOAT", None, None, None),
            expected_type="FLOAT",
        ),
        ShowColumnTypeTestCase(
            description="default-length text",
            show_data_type={
                "type": "TEXT",
                "length": 16777216,
                "byteLength": 16777216,
                "nullable": True,
                "fixed": False,
            },
            information_schema_fields=("TEXT", None, None, 16777216),
            expected_type="VARCHAR(16777216)",
        ),
        ShowColumnTypeTestCase(
            description="bounded text",
            show_data_type={"type": "TEXT", "length": 32, "byteLength": 128, "fixed": False},
            information_schema_fields=("TEXT", None, None, 32),
            expected_type="VARCHAR(32)",
        ),
        ShowColumnTypeTestCase(
            description="fixed-width char",
            show_data_type={"type": "TEXT", "length": 1, "byteLength": 4, "fixed": True},
            information_schema_fields=("TEXT", None, None, 1),
            expected_type="VARCHAR(1)",
        ),
        ShowColumnTypeTestCase(
            description="binary keeps the bare name",
            show_data_type={"type": "BINARY", "length": 8388608, "byteLength": 8388608},
            information_schema_fields=("BINARY", None, None, 8388608),
            expected_type="BINARY",
        ),
        ShowColumnTypeTestCase(
            description="boolean",
            show_data_type={"type": "BOOLEAN", "nullable": True},
            information_schema_fields=("BOOLEAN", None, None, None),
            expected_type="BOOLEAN",
        ),
        ShowColumnTypeTestCase(
            description="date",
            show_data_type={"type": "DATE", "nullable": True},
            information_schema_fields=("DATE", None, None, None),
            expected_type="DATE",
        ),
        ShowColumnTypeTestCase(
            description="time ignores its precision",
            show_data_type={"type": "TIME", "precision": 0, "scale": 9, "nullable": True},
            information_schema_fields=("TIME", None, None, None),
            expected_type="TIME",
        ),
        ShowColumnTypeTestCase(
            description="timestamp without time zone ignores its precision",
            show_data_type={"type": "TIMESTAMP_NTZ", "precision": 0, "scale": 9},
            information_schema_fields=("TIMESTAMP_NTZ", None, None, None),
            expected_type="TIMESTAMP_NTZ",
        ),
        ShowColumnTypeTestCase(
            description="millisecond timestamp without time zone",
            show_data_type={"type": "TIMESTAMP_NTZ", "precision": 0, "scale": 3},
            information_schema_fields=("TIMESTAMP_NTZ", None, None, None),
            expected_type="TIMESTAMP_NTZ",
        ),
        ShowColumnTypeTestCase(
            description="local time zone timestamp",
            show_data_type={"type": "TIMESTAMP_LTZ", "precision": 0, "scale": 9},
            information_schema_fields=("TIMESTAMP_LTZ", None, None, None),
            expected_type="TIMESTAMP_LTZ",
        ),
        ShowColumnTypeTestCase(
            description="offset timestamp",
            show_data_type={"type": "TIMESTAMP_TZ", "precision": 0, "scale": 9},
            information_schema_fields=("TIMESTAMP_TZ", None, None, None),
            expected_type="TIMESTAMP_TZ",
        ),
        ShowColumnTypeTestCase(
            description="variant",
            show_data_type={"type": "VARIANT", "nullable": True},
            information_schema_fields=("VARIANT", None, None, None),
            expected_type="VARIANT",
        ),
        ShowColumnTypeTestCase(
            description="semi-structured object",
            show_data_type={"type": "OBJECT", "nullable": True},
            information_schema_fields=("OBJECT", None, None, None),
            expected_type="OBJECT",
        ),
        ShowColumnTypeTestCase(
            description="semi-structured array",
            show_data_type={"type": "ARRAY", "nullable": True},
            information_schema_fields=("ARRAY", None, None, None),
            expected_type="ARRAY",
        ),
        ShowColumnTypeTestCase(
            description="structured map",
            show_data_type={"type": "MAP", "keyType": {"type": "TEXT"}, "valueType": {}},
            information_schema_fields=("MAP", None, None, None),
            expected_type="MAP",
        ),
        ShowColumnTypeTestCase(
            description="geography",
            show_data_type={"type": "GEOGRAPHY", "nullable": True},
            information_schema_fields=("GEOGRAPHY", None, None, None),
            expected_type="GEOGRAPHY",
        ),
        ShowColumnTypeTestCase(
            description="geometry",
            show_data_type={"type": "GEOMETRY", "nullable": True},
            information_schema_fields=("GEOMETRY", None, None, None),
            expected_type="GEOMETRY",
        ),
        ShowColumnTypeTestCase(
            description="vector",
            show_data_type={"type": "VECTOR", "vectorElementType": "FLOAT", "dimension": 3},
            information_schema_fields=("VECTOR", None, None, None),
            expected_type="VECTOR",
        ),
        ShowColumnTypeTestCase(
            description="decfloat",
            show_data_type={"type": "DECFLOAT", "nullable": True},
            information_schema_fields=("DECFLOAT", None, None, None),
            expected_type="DECFLOAT",
        ),
        ShowColumnTypeTestCase(
            description="file",
            show_data_type={"type": "FILE", "nullable": True},
            information_schema_fields=("FILE", None, None, None),
            expected_type="FILE",
        ),
        ShowColumnTypeTestCase(
            description="lowercase type name",
            show_data_type={"type": "fixed", "precision": 38, "scale": 0},
            information_schema_fields=("number", 38, 0, None),
            expected_type="NUMBER(38,0)",
        ),
        ShowColumnTypeTestCase(
            description="number without precision keeps the bare name",
            show_data_type={"type": "FIXED"},
            information_schema_fields=("NUMBER", None, None, None),
            expected_type="NUMBER",
        ),
        ShowColumnTypeTestCase(
            description="boolean-valued precision is not a precision",
            show_data_type={"type": "FIXED", "precision": True, "scale": 0},
            information_schema_fields=("NUMBER", None, 0, None),
            expected_type="NUMBER",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_column_metadata_when_rendering_type_then_show_matches_information_schema(
    test_case: ShowColumnTypeTestCase,
) -> None:
    data_type, precision, scale, length = test_case.information_schema_fields

    from_show: str = show_columns_type(json.dumps(test_case.show_data_type))
    from_information_schema: str = information_schema_type(
        data_type=data_type,
        numeric_precision=precision,
        numeric_scale=scale,
        character_maximum_length=length,
    )

    assert from_show == test_case.expected_type
    assert from_information_schema == test_case.expected_type


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidShowColumnTypeTestCase(
            description="not json",
            raw_data_type="NUMBER(38,0)",
            expected_error_fragment="invalid type metadata",
        ),
        InvalidShowColumnTypeTestCase(
            description="json array",
            raw_data_type='["FIXED"]',
            expected_error_fragment="invalid type metadata",
        ),
        InvalidShowColumnTypeTestCase(
            description="missing type",
            raw_data_type='{"precision": 38}',
            expected_error_fragment="invalid type metadata",
        ),
        InvalidShowColumnTypeTestCase(
            description="null",
            raw_data_type=None,
            expected_error_fragment="invalid type metadata",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_show_type_when_rendering_then_raises_adapter_error(
    test_case: InvalidShowColumnTypeTestCase,
) -> None:
    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        _ = show_columns_type(test_case.raw_data_type)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
