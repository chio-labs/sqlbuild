from __future__ import annotations

import io

import pytest

from sqlbuild.shared.helpers.status import (
    TransientStatusReporter,
    progress_spinners_disabled,
)
from tests.unit.src.sqlbuild.shared.helpers._test_types import (
    ProgressSpinnersDisabledTestCase,
)
from tests.unit.src.sqlbuild.shared.helpers.helpers import apply_no_progress_env

PROGRESS_SPINNERS_DISABLED_TEST_CASES: tuple[ProgressSpinnersDisabledTestCase, ...] = (
    ProgressSpinnersDisabledTestCase(
        description="unset env keeps spinners enabled",
        env_value=None,
        expected_disabled=False,
    ),
    ProgressSpinnersDisabledTestCase(
        description="truthy '1' disables spinners",
        env_value="1",
        expected_disabled=True,
    ),
    ProgressSpinnersDisabledTestCase(
        description="truthy 'true' is case-insensitive and trimmed",
        env_value="  TRUE  ",
        expected_disabled=True,
    ),
    ProgressSpinnersDisabledTestCase(
        description="truthy 'on' disables spinners",
        env_value="on",
        expected_disabled=True,
    ),
    ProgressSpinnersDisabledTestCase(
        description="falsey '0' keeps spinners enabled",
        env_value="0",
        expected_disabled=False,
    ),
    ProgressSpinnersDisabledTestCase(
        description="arbitrary value keeps spinners enabled",
        env_value="maybe",
        expected_disabled=False,
    ),
    ProgressSpinnersDisabledTestCase(
        description="empty value keeps spinners enabled",
        env_value="",
        expected_disabled=False,
    ),
)


class _TtyStream(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    "test_case",
    PROGRESS_SPINNERS_DISABLED_TEST_CASES,
    ids=[case.description for case in PROGRESS_SPINNERS_DISABLED_TEST_CASES],
)
def test_given_no_progress_env_when_checking_then_reports_expected_disabled_state(
    test_case: ProgressSpinnersDisabledTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_no_progress_env(monkeypatch=monkeypatch, env_value=test_case.env_value)

    assert progress_spinners_disabled() == test_case.expected_disabled


@pytest.mark.parametrize(
    "test_case",
    PROGRESS_SPINNERS_DISABLED_TEST_CASES,
    ids=[case.description for case in PROGRESS_SPINNERS_DISABLED_TEST_CASES],
)
def test_given_no_progress_env_when_building_status_on_tty_then_toggles_spinner(
    test_case: ProgressSpinnersDisabledTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_no_progress_env(monkeypatch=monkeypatch, env_value=test_case.env_value)
    stream: _TtyStream = _TtyStream()

    reporter: TransientStatusReporter = TransientStatusReporter(stream=stream, use_color=False)

    spinner_enabled: bool = reporter._enabled
    assert spinner_enabled == (not test_case.expected_disabled)
