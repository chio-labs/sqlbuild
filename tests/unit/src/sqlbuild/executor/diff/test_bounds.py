from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.models import CursorValue
from sqlbuild.adapter.contract.types import CursorKind
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.diff._helpers.bounds import resolve_bounded_cursors
from sqlbuild.spec.contracts.exceptions import ConfigValueTypeError
from tests.unit.src.sqlbuild.executor.diff._test_types import (
    ResolveBoundedCursorsErrorTestCase,
    ResolveBoundedCursorsTestCase,
    WrongTypedBoundedCursorTestCase,
)
from tests.unit.src.sqlbuild.executor.diff.helpers import (
    assert_cursor_matches_expectation,
    build_fake_model,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveBoundedCursorsTestCase(
            description="returns empty bounds when full diff is requested",
            config_values={"cursor": "event_time", "cursor_type": "timestamp"},
            bounded=None,
            expected_cursor_column=None,
            expected_start_cursor=None,
            expected_end_cursor_kind=None,
            expected_fallback=False,
        ),
        ResolveBoundedCursorsTestCase(
            description="falls back to full when bounded model has no cursor",
            config_values={},
            bounded="30d",
            expected_cursor_column=None,
            expected_start_cursor=None,
            expected_end_cursor_kind=None,
            expected_fallback=True,
        ),
        ResolveBoundedCursorsTestCase(
            description="uses integer bound as lower cursor value",
            config_values={"cursor": "id", "cursor_type": "integer"},
            bounded="100",
            expected_cursor_column="id",
            expected_start_cursor=CursorValue(kind=CursorKind.INTEGER, value=100),
            expected_end_cursor_kind=None,
            expected_fallback=False,
        ),
        ResolveBoundedCursorsTestCase(
            description="uses timestamp duration as bounded window",
            config_values={"cursor": "event_time", "cursor_type": "timestamp"},
            bounded="1d",
            expected_cursor_column="event_time",
            expected_start_cursor=None,
            expected_end_cursor_kind=CursorKind.TIMESTAMP,
            expected_fallback=False,
        ),
        ResolveBoundedCursorsTestCase(
            description="accepts a calendar month duration as bounded window",
            config_values={"cursor": "event_time", "cursor_type": "timestamp"},
            bounded="1mo",
            expected_cursor_column="event_time",
            expected_start_cursor=None,
            expected_end_cursor_kind=CursorKind.TIMESTAMP,
            expected_fallback=False,
        ),
        ResolveBoundedCursorsTestCase(
            description="treats an empty cursor string as present",
            config_values={"cursor": "", "cursor_type": "integer"},
            bounded="10",
            expected_cursor_column="",
            expected_start_cursor=CursorValue(kind=CursorKind.INTEGER, value=10),
            expected_end_cursor_kind=None,
            expected_fallback=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_bounded_diff_config_when_resolving_cursors_then_returns_expected_bounds(
    test_case: ResolveBoundedCursorsTestCase,
) -> None:
    cursor_column: str | None
    start_cursor: CursorValue | None
    end_cursor: CursorValue | None
    fallback: bool
    cursor_column, start_cursor, end_cursor, fallback = resolve_bounded_cursors(
        model=build_fake_model(config_values=test_case.config_values),
        bounded=test_case.bounded,
    )

    assert cursor_column == test_case.expected_cursor_column
    assert_cursor_matches_expectation(
        cursor=start_cursor,
        expected_cursor=test_case.expected_start_cursor,
        expected_kind=test_case.expected_end_cursor_kind,
    )
    assert_cursor_matches_expectation(
        cursor=end_cursor,
        expected_cursor=None,
        expected_kind=test_case.expected_end_cursor_kind,
    )
    assert fallback == test_case.expected_fallback


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveBoundedCursorsErrorTestCase(
            description="rejects non integer bound for integer cursor",
            config_values={"cursor": "id", "cursor_type": "integer"},
            bounded="30d",
            expected_error_fragment="requires an integer bound",
            expected_code="X102",
        ),
        ResolveBoundedCursorsErrorTestCase(
            description="rejects invalid timestamp duration",
            config_values={"cursor": "event_time", "cursor_type": "timestamp"},
            bounded="30x",
            expected_error_fragment="requires duration like",
            expected_code="X103",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_bounded_diff_config_when_resolving_cursors_then_raises_clear_error(
    test_case: ResolveBoundedCursorsErrorTestCase,
) -> None:
    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment) as error_info:
        resolve_bounded_cursors(
            model=build_fake_model(config_values=test_case.config_values),
            bounded=test_case.bounded,
        )

    assert error_info.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        WrongTypedBoundedCursorTestCase(
            description="integer cursor column",
            config_values={"cursor": 7, "cursor_type": "integer"},
            bounded="10",
            expected_key="cursor",
            expected_type="a string",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_wrong_typed_cursor_when_resolving_bounded_diff_then_raises_config_error(
    test_case: WrongTypedBoundedCursorTestCase,
) -> None:
    with pytest.raises(ConfigValueTypeError) as error_info:
        resolve_bounded_cursors(
            model=build_fake_model(config_values=test_case.config_values),
            bounded=test_case.bounded,
        )

    assert error_info.value.key == test_case.expected_key
    assert error_info.value.expected == test_case.expected_type
    assert error_info.value.actual_type is int
