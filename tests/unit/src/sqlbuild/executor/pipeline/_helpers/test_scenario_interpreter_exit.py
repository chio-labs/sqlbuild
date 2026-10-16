import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from tests.unit.src.sqlbuild.executor.pipeline._helpers._test_types import (
    ScenarioWorkerExitTestCase,
)

_ABANDONED_WORKERS: str = dedent(
    """
    import sys
    import time
    import types
    from concurrent.futures import Future


    class SlowFinalizer:
        def __del__(self):
            print("finalizing", sys.is_finalizing(), file=sys.stderr, flush=True)
            time.sleep(1.5)


    holder = types.ModuleType("holder")
    holder.finalizer = SlowFinalizer()
    sys.modules["holder"] = holder

    from sqlbuild._native import invert_edges
    from sqlbuild.executor.pipeline._helpers.scenario import _start_scenario_workers


    def slow_key(item):
        time.sleep(1.0)
        return item


    def run(*, scenario, notify_start):
        return invert_edges(edges={"a": ("b",), "c": ("b",)}, sort_key=slow_key)


    count = int(sys.argv[1])
    scenarios = tuple(f"scenario_{index}" for index in range(count))
    futures = tuple(Future() for _ in scenarios)
    _start_scenario_workers(scenarios=scenarios, futures=futures, run=run, worker_count=count)
    time.sleep(0.3)
    """
)


@pytest.mark.parametrize(
    "test_case",
    (
        ScenarioWorkerExitTestCase("one abandoned worker inside native code", 1, 0),
        ScenarioWorkerExitTestCase("several abandoned workers inside native code", 3, 0),
    ),
    ids=lambda case: case.description,
)
def test_given_abandoned_scenario_workers_when_interpreter_finalizes_then_process_exits_cleanly(
    test_case: ScenarioWorkerExitTestCase,
    tmp_path: Path,
) -> None:
    script: Path = tmp_path / "scenario_exit.py"
    script.write_text(_ABANDONED_WORKERS, encoding="utf-8")

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, str(script), str(test_case.worker_count)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr
    assert "finalizing True" in result.stderr
    assert "Waiting up to 5s for running scenario statements to stop" in result.stderr
