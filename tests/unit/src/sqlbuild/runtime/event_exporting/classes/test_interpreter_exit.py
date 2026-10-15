import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from tests.unit.src.sqlbuild.runtime.event_exporting.classes._test_types import (
    InterpreterExitTestCase,
)

_FINALIZING_WORK: str = dedent(
    """
    import sys
    import time
    import types


    class SlowFinalizer:
        def __del__(self):
            print("finalizing", sys.is_finalizing(), file=sys.stderr, flush=True)
            time.sleep(0.6)


    holder = types.ModuleType("holder")
    holder.finalizer = SlowFinalizer()
    sys.modules["holder"] = holder
    """
)


@pytest.mark.parametrize(
    "test_case",
    (
        InterpreterExitTestCase(
            "summary callback still running at exit",
            dedent(
                """
                from sqlbuild._native import EventExporterDispatcher

                def summarize(summary):
                    time.sleep(0.2)

                EventExporterDispatcher(exporters=(), summary_callback=summarize).shutdown()
                """
            ),
            0,
        ),
        InterpreterExitTestCase(
            "timed-out sink still running at exit",
            dedent(
                """
                from types import SimpleNamespace

                from sqlbuild._native import BoundEventExporter, EventExporterDispatcher

                def slow(*, event):
                    time.sleep(0.3)

                dispatcher = EventExporterDispatcher(
                    exporters=(BoundEventExporter("slow", slow, {}),),
                    shutdown_timeout_seconds=0.0,
                    failure_callback=lambda failure: None,
                )
                dispatcher.enqueue(SimpleNamespace(event_type="statement_submitted"))
                time.sleep(0.05)
                dispatcher.shutdown()
                """
            ),
            0,
        ),
        InterpreterExitTestCase(
            "dispatcher never shut down",
            dedent(
                """
                from sqlbuild._native import EventExporterDispatcher

                dispatcher = EventExporterDispatcher(
                    exporters=(), summary_callback=print, health_interval_seconds=0.01
                )
                """
            ),
            0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_live_exporter_threads_when_interpreter_finalizes_then_process_exits_cleanly(
    test_case: InterpreterExitTestCase,
    tmp_path: Path,
) -> None:
    script: Path = tmp_path / "exporter_exit.py"
    script.write_text(_FINALIZING_WORK + test_case.script, encoding="utf-8")

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr
    assert "finalizing True" in result.stderr
