from __future__ import annotations

import io

import pytest

from sqlbuild._native import TransientStatusReporter
from sqlbuild.presentation.main._progress_spinners_disabled import progress_spinners_disabled
from tests.unit.src.sqlbuild.presentation.classes._test_types import (
    ProgressSpinnersDisabledTestCase,
    StatusReporterOutputTestCase,
)
from tests.unit.src.sqlbuild.presentation.classes.helpers import (
    RecordingStream,
    apply_no_progress_env,
    drive_status_reporter,
    persistent_lines,
)


class _TtyStream(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    "test_case",
    (
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
    ),
    ids=lambda case: case.description,
)
def test_given_no_progress_env_when_checking_then_reports_expected_disabled_state(
    test_case: ProgressSpinnersDisabledTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_no_progress_env(monkeypatch=monkeypatch, env_value=test_case.env_value)

    assert progress_spinners_disabled() == test_case.expected_disabled


@pytest.mark.parametrize(
    "test_case",
    (
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
    ),
    ids=lambda case: case.description,
)
def test_given_no_progress_env_when_building_status_on_tty_then_toggles_spinner(
    test_case: ProgressSpinnersDisabledTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_no_progress_env(monkeypatch=monkeypatch, env_value=test_case.env_value)
    stream: _TtyStream = _TtyStream()

    reporter: TransientStatusReporter = TransientStatusReporter(stream=stream, use_color=False)
    reporter.start("Working...")
    reporter.close()

    assert ("Working...\n" in stream.getvalue()) == test_case.expected_disabled


@pytest.mark.parametrize(
    "test_case",
    (
        StatusReporterOutputTestCase(
            description="plain stream writes every message as a muted line",
            use_color=True,
            tty=False,
            expected_persistent_lines=(
                "\x1b[2mDiscovering project...\x1b[0m",
                "\x1b[2mCompiling project graph...\x1b[0m",
                "\x1b[2mCompiled project graph. (0.1s)\x1b[0m",
                "",
                "\x1b[2mResolving tests...\x1b[0m",
                "\x1b[2mPrepared 2 tests\x1b[0m",
                "",
                "\x1b[2mFormatting SQL...\x1b[0m",
                "Formatting SQL  ERROR",
                "styled",
                "",
            ),
        ),
        StatusReporterOutputTestCase(
            description="terminal erases live status and keeps only completions",
            use_color=False,
            tty=True,
            expected_persistent_lines=(
                "Compiled project graph. (0.1s)",
                "",
                "Prepared 2 tests",
                "",
                "Formatting SQL  ERROR",
                "styled",
                "",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_status_sequence_when_reporting_then_writes_expected_persistent_lines(
    test_case: StatusReporterOutputTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SQLBUILD_NO_PROGRESS", raising=False)
    stream: RecordingStream = RecordingStream(events=[], tty=test_case.tty)
    reporter: TransientStatusReporter = TransientStatusReporter(
        stream=stream, use_color=test_case.use_color
    )

    drive_status_reporter(reporter)

    assert persistent_lines(stream.getvalue()) == test_case.expected_persistent_lines
