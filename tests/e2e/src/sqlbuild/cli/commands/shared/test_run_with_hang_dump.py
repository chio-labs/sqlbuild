"""A hung command fails its own test with every Python thread's stack instead of hanging the run."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.shared._test_types import (
    FinishedCommandTestCase,
    HangDumpTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_with_hang_dump


@pytest.mark.parametrize(
    "test_case",
    [
        HangDumpTestCase(
            description="main thread joins a worker blocked forever",
            script=(
                "import threading\n"
                "def blocked_worker_wait():\n"
                "    threading.Event().wait()\n"
                "def joining_main_thread():\n"
                "    worker = threading.Thread(target=blocked_worker_wait)\n"
                "    worker.start()\n"
                "    print('started', flush=True)\n"
                "    worker.join()\n"
                "joining_main_thread()\n"
            ),
            expected_fragments=("started", "blocked_worker_wait", "joining_main_thread"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_hung_python_command_when_running_with_hang_dump_then_fails_with_thread_stacks(
    test_case: HangDumpTestCase, tmp_path: Path
) -> None:
    started: float = time.monotonic()
    with pytest.raises(AssertionError) as raised:
        run_with_hang_dump(
            argv=(sys.executable, "-c", test_case.script),
            cwd=tmp_path,
            env={**os.environ, "PYTHONFAULTHANDLER": "1"},
            input_text=None,
            timeout_seconds=2.0,
        )

    message: str = str(raised.value)
    assert "did not finish within 2s" in message
    assert [fragment in message for fragment in test_case.expected_fragments] == [True] * len(
        test_case.expected_fragments
    ), message
    assert time.monotonic() - started < 30.0


@pytest.mark.parametrize(
    "test_case",
    [
        FinishedCommandTestCase(
            description="input reaches the command and its exit code and output return",
            script="import sys; sys.stdout.write(sys.stdin.read().upper()); sys.exit(3)",
            input_text="orders\n",
            expected_result=(3, "ORDERS\n", ""),
        ),
        FinishedCommandTestCase(
            description="without input the command reads end of input",
            script="import sys; print(repr(sys.stdin.read()))",
            input_text=None,
            expected_result=(0, "''\n", ""),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_finishing_command_when_running_with_hang_dump_then_returns_its_result(
    test_case: FinishedCommandTestCase, tmp_path: Path
) -> None:
    completed: subprocess.CompletedProcess[str] = run_with_hang_dump(
        argv=(sys.executable, "-c", test_case.script),
        cwd=tmp_path,
        env=dict(os.environ),
        input_text=test_case.input_text,
        timeout_seconds=60.0,
    )

    assert (completed.returncode, completed.stdout, completed.stderr) == test_case.expected_result


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
