from __future__ import annotations

import io
import os
import re
from collections.abc import Callable
from types import MappingProxyType
from typing import cast

import pytest

from sqlbuild._native import TransientStatusReporter


def _delete_no_progress_env(monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    del env_value
    monkeypatch.delenv("SQLBUILD_NO_PROGRESS", raising=False)


def _set_no_progress_env(monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    monkeypatch.setenv("SQLBUILD_NO_PROGRESS", cast(str, env_value))


def apply_no_progress_env(*, monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    _NO_PROGRESS_ENV_ACTIONS[env_value is None](monkeypatch, env_value)


_NO_PROGRESS_ENV_ACTIONS: MappingProxyType[
    bool, Callable[[pytest.MonkeyPatch, str | None], None]
] = MappingProxyType({True: _delete_no_progress_env, False: _set_no_progress_env})


class RecordingStream(io.StringIO):
    """In-memory stream that records writes into a shared event log."""

    def __init__(self, *, events: list[str], tty: bool) -> None:
        super().__init__()
        self._events: list[str] = events
        self._tty: bool = tty

    def isatty(self) -> bool:
        return self._tty

    def write(self, text: str) -> int:
        self._events.append(f"write:{text}")
        return super().write(text)


class RecordingSpinnerOwner:
    """Transient line owner that records clear and redraw requests."""

    def __init__(self, *, events: list[str]) -> None:
        self._events: list[str] = events

    def clear_transient_line(self) -> None:
        self._events.append("clear")

    def redraw_transient_line(self) -> None:
        self._events.append("redraw")


def drive_status_reporter(reporter: TransientStatusReporter) -> None:
    """Run one start, update, completion, preflight and error sequence."""

    reporter.start("Discovering project...")
    reporter.update("Compiling project graph...")
    reporter.complete(message="Compiled project graph. (0.1s)", blank_line_after=True)
    reporter.report_preflight_progress("Resolving tests...")
    reporter.report_preflight_progress("Prepared 2 tests")
    reporter.start("Formatting SQL...")
    reporter.error("Formatting SQL  ERROR")
    reporter.complete_styled(message="styled")
    reporter.close()


def persistent_lines(text: str) -> tuple[str, ...]:
    """The lines left after transient status lines are erased."""

    without_cursor: str = re.sub(r"\x1b\[\?25[hl]", "", text)
    return tuple(line.rsplit("\x1b[K", 1)[-1] for line in without_cursor.split("\n"))


SLOW_FINALIZATION_SCRIPT: str = (
    "class SlowFinalizer:\n"
    "    def __init__(self):\n"
    "        self.cycle = self\n"
    "    def __del__(self):\n"
    "        time.sleep(0.5)\n"
    "SlowFinalizer()\n"
)
OPEN_SPINNER_SCRIPT: str = (
    "import io, time\n"
    "from sqlbuild._native import TransientStatusReporter\n"
    "class Tty(io.StringIO):\n"
    "    def isatty(self):\n"
    "        return True\n"
    "reporter = TransientStatusReporter(stream=Tty())\n"
    "reporter.start('Working...')\n"
    "time.sleep(0.35)\n"
) + SLOW_FINALIZATION_SCRIPT
OPEN_NESTED_SPINNER_SCRIPT: str = (
    "import io, time\n"
    "from sqlbuild._native import NestedCommandProgressCallbacks\n"
    "class Tty(io.StringIO):\n"
    "    def isatty(self):\n"
    "        return True\n"
    "reporter = NestedCommandProgressCallbacks(\n"
    "    total=1, label='audits', stream=Tty(), use_color=False\n"
    ")\n"
    "reporter.on_item_start(group_name='orders', item_name='not_null')\n"
) + SLOW_FINALIZATION_SCRIPT


def without_no_progress_env() -> dict[str, str]:
    """The current environment with progress spinners left enabled."""

    environment: dict[str, str] = dict(os.environ)
    environment.pop("SQLBUILD_NO_PROGRESS", None)
    return environment
