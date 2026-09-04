from __future__ import annotations

import pytest

from sqlbuild.spec.contracts.exceptions import ConfigValueTypeError
from sqlbuild.spec.contracts.main.get_config_bool import get_config_bool
from sqlbuild.spec.contracts.main.get_config_cursor_bound import get_config_cursor_bound
from sqlbuild.spec.contracts.main.get_config_int import get_config_int
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.main.get_config_string_tuple import get_config_string_tuple
from tests.unit.src.sqlbuild.spec.contracts._helpers._test_types import (
    ConfigValueErrorTestCase,
    ConfigValueSuccessTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ConfigValueSuccessTestCase("absent string", get_config_str, {}, "cursor", None),
        ConfigValueSuccessTestCase(
            "present null string is absent", get_config_str, {"cursor": None}, "cursor", None
        ),
        ConfigValueSuccessTestCase("absent boolean", get_config_bool, {}, "enabled", None),
        ConfigValueSuccessTestCase(
            "absent string tuple", get_config_string_tuple, {}, "columns", None
        ),
        ConfigValueSuccessTestCase("absent integer", get_config_int, {}, "batch_concurrency", None),
        ConfigValueSuccessTestCase(
            "present empty string", get_config_str, {"cursor": ""}, "cursor", ""
        ),
        ConfigValueSuccessTestCase(
            "present string", get_config_str, {"cursor": "event_at"}, "cursor", "event_at"
        ),
        ConfigValueSuccessTestCase(
            "present false boolean", get_config_bool, {"enabled": False}, "enabled", False
        ),
        ConfigValueSuccessTestCase(
            "present string list",
            get_config_string_tuple,
            {"columns": ["id", "event_at"]},
            "columns",
            ("id", "event_at"),
        ),
        ConfigValueSuccessTestCase(
            "present integer",
            get_config_int,
            {"batch_concurrency": 2},
            "batch_concurrency",
            2,
        ),
        ConfigValueSuccessTestCase(
            "integer cursor bound normalization",
            get_config_cursor_bound,
            {"cursor_start": 30},
            "cursor_start",
            "30",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_config_when_extracting_then_returns_typed_value(
    test_case: ConfigValueSuccessTestCase,
) -> None:
    assert test_case.getter(values=test_case.values, key=test_case.key) == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        ConfigValueErrorTestCase("integer string", get_config_str, "cursor", "a string", 7),
        ConfigValueErrorTestCase(
            "string boolean", get_config_bool, "enabled", "a boolean", "false"
        ),
        ConfigValueErrorTestCase(
            "mixed string list",
            get_config_string_tuple,
            "columns",
            "a list or tuple of strings",
            ["id", 7],
        ),
        ConfigValueErrorTestCase(
            "boolean integer", get_config_int, "batch_concurrency", "an integer", True
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_wrong_typed_present_value_when_extracting_then_raises_structured_error(
    test_case: ConfigValueErrorTestCase,
) -> None:
    with pytest.raises(ConfigValueTypeError) as error_info:
        test_case.getter(values={test_case.key: test_case.value}, key=test_case.key)

    assert error_info.value.key == test_case.key
    assert error_info.value.expected == test_case.expected_type
    assert error_info.value.actual_type is type(test_case.value)
    assert str(error_info.value) == (
        f"config key '{test_case.key}' expected {test_case.expected_type}, "
        f"got {type(test_case.value).__name__}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
