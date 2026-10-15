import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from tests.unit.src.sqlbuild.runtime.output_capture.classes._test_types import (
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
            time.sleep(1.5)


    holder = types.ModuleType("holder")
    holder.finalizer = SlowFinalizer()
    sys.modules["holder"] = holder
    """
)
_SLOW_SINK: str = dedent(
    """
    from sqlbuild._native import (
        EventExporterCommandScope,
        EventExporterDispatcher,
        OutputCaptureDispatcher,
    )
    from sqlbuild.runtime.output_capture.models import BoundCommandOutputSink
    from sqlbuild.runtime.output_capture.types import CommandOutputStream

    def slow(*, record):
        time.sleep(1.0)

    exporters = EventExporterDispatcher(exporters=())
    exporters.bind_command_output_sinks(
        (
            BoundCommandOutputSink(
                name="slow",
                function=slow,
                provider_arguments={},
                streams=frozenset(CommandOutputStream),
            ),
        )
    )
    output = OutputCaptureDispatcher(
        exporter=EventExporterCommandScope(dispatcher=exporters),
        invocation_id="invocation",
        shutdown_timeout_seconds=0.0,
    )
    output.append(stream=CommandOutputStream.STDOUT, text="hello\\n")
    time.sleep(0.35)
    """
)


@pytest.mark.parametrize(
    "test_case",
    (
        InterpreterExitTestCase(
            "slow sink still running after close",
            _SLOW_SINK + "output.close()\n",
            0,
        ),
        InterpreterExitTestCase("capture never closed", _SLOW_SINK, 0),
    ),
    ids=lambda case: case.description,
)
def test_given_slow_command_output_sink_when_interpreter_finalizes_then_process_exits_cleanly(
    test_case: InterpreterExitTestCase,
    tmp_path: Path,
) -> None:
    script: Path = tmp_path / "output_exit.py"
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
