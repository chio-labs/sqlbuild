"""Tests for canonical Python check terminal projection."""

from __future__ import annotations

from contextvars import Token
from io import StringIO

import pytest

from sqlbuild._native import NativeProgressProjector, write_check_results
from tests.unit.src.sqlbuild.cli.commands._helpers.check._test_types import (
    CheckOutputProjectionCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.check.helpers import (
    check_results,
    publish_check_attempt,
)


class _FailBeforeSecondCheckStream(StringIO):
    def write(self, text: str) -> int:
        if text.startswith("  check     second") and "PASS" in text:
            raise OSError("controlled check output failure")
        return super().write(text)


@pytest.mark.parametrize(
    "test_case",
    (
        CheckOutputProjectionCase(
            description="normal grouped output claims canonical durations without duplicates",
            expected_first_duration="0.10s",
            expected_second_duration="0.20s",
            expected_generic_terminal_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_completed_checks_when_grouped_rows_render_then_terminals_are_claimed_once(
    test_case: CheckOutputProjectionCase,
) -> None:
    stream: StringIO = StringIO()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    projector.configure_resources(ordinals={"first": 1, "second": 2}, total=2)
    publish_check_attempt(projector=projector, name="first", duration_ms=100)
    publish_check_attempt(projector=projector, name="second", duration_ms=200)
    token: Token[NativeProgressProjector | None] = projector.install()
    try:
        write_check_results(stream=stream, results=check_results(), use_color=False)
    finally:
        projector.restore(token)
    projector.close()
    output: str = stream.getvalue()

    assert f"PASS  {test_case.expected_first_duration}" in output
    assert f"PASS  {test_case.expected_second_duration}" in output
    assert output.count("check     first OK") == test_case.expected_generic_terminal_count
    assert output.count("check     second OK") == test_case.expected_generic_terminal_count


@pytest.mark.parametrize(
    "test_case",
    (
        CheckOutputProjectionCase(
            description="failure before second row leaves only second terminal for close",
            expected_first_duration="0.10s",
            expected_second_duration="0.20s",
            expected_generic_terminal_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_two_completed_checks_when_second_row_fails_then_close_renders_unclaimed_terminal(
    test_case: CheckOutputProjectionCase,
) -> None:
    stream: _FailBeforeSecondCheckStream = _FailBeforeSecondCheckStream()
    projector: NativeProgressProjector = NativeProgressProjector(stream=stream, use_color=False)
    projector.configure_resources(ordinals={"first": 1, "second": 2}, total=2)
    publish_check_attempt(projector=projector, name="first", duration_ms=100)
    publish_check_attempt(projector=projector, name="second", duration_ms=200)
    token: Token[NativeProgressProjector | None] = projector.install()
    with pytest.raises(OSError, match="controlled check output failure"):
        write_check_results(stream=stream, results=check_results(), use_color=False)
    projector.restore(token)
    projector.close()
    output: str = stream.getvalue()

    assert test_case.expected_first_duration in output
    assert output.count("check     first OK") == 0
    assert output.count(f"check     second OK {test_case.expected_second_duration}") == (
        test_case.expected_generic_terminal_count
    )
