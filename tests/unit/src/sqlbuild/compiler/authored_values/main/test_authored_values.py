from __future__ import annotations

import pytest

from tests.unit.src.sqlbuild.compiler.authored_values.main._test_types import (
    AuthoredValueErrorTestCase,
    AuthoredValueTestCase,
)
from tests.unit.src.sqlbuild.compiler.authored_values.main.helpers import (
    AuthoredValueTestError,
    parse_named_bool_default_false,
    parse_named_bool_default_none,
    parse_named_string,
    parse_optional_bool,
    parse_optional_mapping,
    parse_optional_string,
    parse_optional_string_tuple,
    parse_required_string,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AuthoredValueTestCase(
            description="required string keeps surrounding whitespace",
            parse=parse_required_string,
            raw_value=" orders ",
            expected_value=" orders ",
        ),
        AuthoredValueTestCase(
            description="optional string defaults to none",
            parse=parse_optional_string,
            raw_value=None,
            expected_value=None,
        ),
        AuthoredValueTestCase(
            description="optional string returns value",
            parse=parse_optional_string,
            raw_value="orders",
            expected_value="orders",
        ),
        AuthoredValueTestCase(
            description="named string defaults to none",
            parse=parse_named_string,
            raw_value=None,
            expected_value=None,
        ),
        AuthoredValueTestCase(
            description="optional bool defaults to none",
            parse=parse_optional_bool,
            raw_value=None,
            expected_value=None,
        ),
        AuthoredValueTestCase(
            description="optional bool returns false",
            parse=parse_optional_bool,
            raw_value=False,
            expected_value=False,
        ),
        AuthoredValueTestCase(
            description="named bool uses false default",
            parse=parse_named_bool_default_false,
            raw_value=None,
            expected_value=False,
        ),
        AuthoredValueTestCase(
            description="named bool uses none default",
            parse=parse_named_bool_default_none,
            raw_value=None,
            expected_value=None,
        ),
        AuthoredValueTestCase(
            description="named bool returns true over default",
            parse=parse_named_bool_default_false,
            raw_value=True,
            expected_value=True,
        ),
        AuthoredValueTestCase(
            description="optional mapping defaults to empty",
            parse=parse_optional_mapping,
            raw_value=None,
            expected_value={},
        ),
        AuthoredValueTestCase(
            description="optional mapping returns value",
            parse=parse_optional_mapping,
            raw_value={"region": "west"},
            expected_value={"region": "west"},
        ),
        AuthoredValueTestCase(
            description="optional string list defaults to empty",
            parse=parse_optional_string_tuple,
            raw_value=None,
            expected_value=(),
        ),
        AuthoredValueTestCase(
            description="optional string list returns tuple",
            parse=parse_optional_string_tuple,
            raw_value=["orders", "customers"],
            expected_value=("orders", "customers"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_authored_value_when_parsing_then_returns_expected_value(
    test_case: AuthoredValueTestCase,
) -> None:
    assert test_case.parse(test_case.raw_value) == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        AuthoredValueErrorTestCase(
            description="required string rejects missing value",
            parse=parse_required_string,
            raw_value=None,
            expected_message=(
                "models/orders.yml model 'orders' must define non-empty string 'setting'"
            ),
        ),
        AuthoredValueErrorTestCase(
            description="optional string rejects blank value",
            parse=parse_optional_string,
            raw_value="  ",
            expected_message="models/orders.yml model 'orders' 'setting' must be a non-empty string",
        ),
        AuthoredValueErrorTestCase(
            description="named string rejects non-string value",
            parse=parse_named_string,
            raw_value=3,
            expected_message="models/orders.yml model 'orders' 'setting' must be a non-empty string",
        ),
        AuthoredValueErrorTestCase(
            description="optional bool rejects string value",
            parse=parse_optional_bool,
            raw_value="yes",
            expected_message="models/orders.yml model 'orders' 'setting' must be a boolean",
        ),
        AuthoredValueErrorTestCase(
            description="named bool rejects integer value",
            parse=parse_named_bool_default_false,
            raw_value=1,
            expected_message="models/orders.yml model 'orders' 'setting' must be a boolean",
        ),
        AuthoredValueErrorTestCase(
            description="optional mapping rejects list value",
            parse=parse_optional_mapping,
            raw_value=["region"],
            expected_message="models/orders.yml model 'orders' 'setting' must be a mapping",
        ),
        AuthoredValueErrorTestCase(
            description="optional string list rejects mapping value",
            parse=parse_optional_string_tuple,
            raw_value={"region": "west"},
            expected_message="models/orders.yml model 'orders' 'setting' must be a list",
        ),
        AuthoredValueErrorTestCase(
            description="optional string list rejects non-string entries",
            parse=parse_optional_string_tuple,
            raw_value=["orders", 3],
            expected_message="models/orders.yml model 'orders' 'setting' entries must be strings",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_authored_value_when_parsing_then_raises_injected_error(
    test_case: AuthoredValueErrorTestCase,
) -> None:
    with pytest.raises(AuthoredValueTestError) as error:
        test_case.parse(test_case.raw_value)

    assert str(error.value) == test_case.expected_message
