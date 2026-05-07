from __future__ import annotations

from decimal import Decimal

import pytest

from sqlbuild.adapter.shared.models import RowDiffTolerance, RowDiffTolerances
from sqlbuild.executor.diff.helpers.config import parse_row_diff_tolerances
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from tests.unit.src.sqlbuild.executor.diff._test_types import (
    ParseRowDiffTolerancesErrorTestCase,
    ParseRowDiffTolerancesTestCase,
)

PARSE_ROW_DIFF_TOLERANCES_TEST_CASES: list[ParseRowDiffTolerancesTestCase] = [
    ParseRowDiffTolerancesTestCase(
        description="parses decimal tolerances by type and by column",
        raw={
            "by_type": {
                "FLOAT": {"relative": 0.0001, "absolute": "0.000001"},
                "integer": {"absolute": 1},
            },
            "by_column": {
                "revenue": {"absolute": "0.01"},
                "conversion_rate": {"relative": "0.001", "absolute": "0.0001"},
            },
        },
        expected_result=RowDiffTolerances(
            by_type={
                "float": RowDiffTolerance(
                    relative=Decimal("0.0001"),
                    absolute=Decimal("0.000001"),
                ),
                "integer": RowDiffTolerance(absolute=Decimal("1")),
            },
            by_column={
                "revenue": RowDiffTolerance(absolute=Decimal("0.01")),
                "conversion_rate": RowDiffTolerance(
                    relative=Decimal("0.001"),
                    absolute=Decimal("0.0001"),
                ),
            },
        ),
    ),
    ParseRowDiffTolerancesTestCase(
        description="returns empty tolerances for none",
        raw=None,
        expected_result=RowDiffTolerances(),
    ),
]

PARSE_ROW_DIFF_TOLERANCES_ERROR_TEST_CASES: list[ParseRowDiffTolerancesErrorTestCase] = [
    ParseRowDiffTolerancesErrorTestCase(
        description="rejects non mapping root",
        raw=[],
        expected_error_fragment="row_diff_tolerances must be a mapping",
        expected_code="X401",
    ),
    ParseRowDiffTolerancesErrorTestCase(
        description="rejects empty tolerance rule",
        raw={"by_column": {"revenue": {}}},
        expected_error_fragment="must define absolute or relative",
        expected_code="X404",
    ),
    ParseRowDiffTolerancesErrorTestCase(
        description="rejects unsupported rule keys",
        raw={"by_type": {"float": {"disabled": True}}},
        expected_error_fragment="contains unsupported keys: disabled",
        expected_code="X403",
    ),
    ParseRowDiffTolerancesErrorTestCase(
        description="rejects boolean threshold",
        raw={"by_column": {"revenue": {"absolute": True}}},
        expected_error_fragment="absolute must be numeric",
        expected_code="X405",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PARSE_ROW_DIFF_TOLERANCES_TEST_CASES,
    ids=[case.description for case in PARSE_ROW_DIFF_TOLERANCES_TEST_CASES],
)
def test_given_raw_row_diff_tolerances_when_parsing_then_returns_typed_tolerances(
    test_case: ParseRowDiffTolerancesTestCase,
) -> None:
    result: RowDiffTolerances = parse_row_diff_tolerances(test_case.raw)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    PARSE_ROW_DIFF_TOLERANCES_ERROR_TEST_CASES,
    ids=[case.description for case in PARSE_ROW_DIFF_TOLERANCES_ERROR_TEST_CASES],
)
def test_given_invalid_row_diff_tolerances_when_parsing_then_raises_clear_error(
    test_case: ParseRowDiffTolerancesErrorTestCase,
) -> None:
    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment) as error_info:
        parse_row_diff_tolerances(test_case.raw)

    assert error_info.value.code == test_case.expected_code
