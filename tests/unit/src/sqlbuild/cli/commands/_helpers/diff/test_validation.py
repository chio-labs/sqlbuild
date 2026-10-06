"""Diff target range parsing."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.diff.validation import parse_diff_name_range
from sqlbuild.cli.commands.exceptions import CliUserError
from tests.unit.src.sqlbuild.cli.commands._helpers.diff._test_types import (
    ParseDiffNameRangeErrorTestCase,
    ParseDiffNameRangeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParseDiffNameRangeTestCase(
            description="explicit range keeps both targets",
            name_range="prod:dev",
            expected_result=("prod", "dev"),
        ),
        ParseDiffNameRangeTestCase(
            description="bare target leaves TO for the active target",
            name_range="prod",
            expected_result=("prod", None),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_range_when_parsing_then_returns_from_and_optional_to(
    test_case: ParseDiffNameRangeTestCase,
) -> None:
    assert parse_diff_name_range(test_case.name_range) == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        ParseDiffNameRangeErrorTestCase(
            description="missing range", name_range=None, expected_code="C208"
        ),
        ParseDiffNameRangeErrorTestCase(
            description="empty target", name_range="", expected_code="C209"
        ),
        ParseDiffNameRangeErrorTestCase(
            description="empty TO", name_range="prod:", expected_code="C209"
        ),
        ParseDiffNameRangeErrorTestCase(
            description="empty FROM", name_range=":dev", expected_code="C209"
        ),
        ParseDiffNameRangeErrorTestCase(
            description="too many separators", name_range="a:b:c", expected_code="C209"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_target_range_when_parsing_then_raises_coded_error(
    test_case: ParseDiffNameRangeErrorTestCase,
) -> None:
    with pytest.raises(CliUserError) as error_info:
        parse_diff_name_range(test_case.name_range)

    assert error_info.value.code == test_case.expected_code


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
