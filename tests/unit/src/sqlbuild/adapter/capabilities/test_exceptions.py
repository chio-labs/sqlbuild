"""Tests for public adapter exceptions."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.exceptions import AdapterUserError
from tests.unit.src.sqlbuild.adapter.capabilities._test_types import AdapterUserErrorTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterUserErrorTestCase(
            description="accepts the ordinary positional exception message",
            message="adapter operation failed",
            code="A123",
            help="check adapter configuration",
            expected_args=("adapter operation failed",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_user_error_fields_when_constructing_then_preserves_exception_semantics(
    test_case: AdapterUserErrorTestCase,
) -> None:
    error: AdapterUserError = AdapterUserError(
        test_case.message,
        code=test_case.code,
        help=test_case.help,
    )

    assert error.args == test_case.expected_args
    assert error.message == test_case.message
    assert error.code == test_case.code
    assert error.help == test_case.help
