from __future__ import annotations

from collections.abc import Callable

import pytest

from sqlbuild.compiler.macro_bridge.main.active_macro_bridge import active_macro_bridge
from sqlbuild.compiler.macro_bridge.main.run_with_macro_bridge import run_with_macro_bridge
from tests.unit.src.sqlbuild.compiler.macro_bridge.main._test_types import (
    MacroBridgeFailureTestCase,
    MacroBridgeSuccessTestCase,
)
from tests.unit.src.sqlbuild.compiler.macro_bridge.main.helpers import (
    failed,
    failed_after_scan,
    mismatched_after_scan,
    recording_failure,
    recording_stage,
    rendered,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MacroBridgeSuccessTestCase(
            description="success runs once with the bridge",
            expected_result="rendered",
            expected_bridged_runs=[True],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_succeeding_stage_when_running_with_macro_bridge_then_runs_once_bridged(
    test_case: MacroBridgeSuccessTestCase,
) -> None:
    runs: list[bool] = []

    result: str = run_with_macro_bridge(stage=recording_stage(runs=runs, stages={True: rendered}))

    assert result == test_case.expected_result
    assert runs == test_case.expected_bridged_runs
    assert active_macro_bridge() is None


@pytest.mark.parametrize(
    "test_case",
    [
        MacroBridgeFailureTestCase(
            description="failure after a scan raises the stage error without a re-run",
            stage_with_bridge=failed_after_scan,
            expected_error_message="render failed",
            expected_bridged_runs=[True],
        ),
        MacroBridgeFailureTestCase(
            description="failure before the bridge scans anything raises without a re-run",
            stage_with_bridge=failed,
            expected_error_message="render failed",
            expected_bridged_runs=[True],
        ),
        MacroBridgeFailureTestCase(
            description="a bridge mismatch after a scan stays an explicit mismatch",
            stage_with_bridge=mismatched_after_scan,
            expected_error_message="native scan ended early",
            expected_bridged_runs=[True],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_stage_when_running_with_macro_bridge_then_raises_its_error_once(
    test_case: MacroBridgeFailureTestCase,
) -> None:
    runs: list[bool] = []
    raised_errors: list[Exception] = []
    stage: Callable[[], str] = recording_stage(
        runs=runs,
        stages={True: recording_failure(stage=test_case.stage_with_bridge, errors=raised_errors)},
    )

    with pytest.raises(Exception) as raised:
        _ = run_with_macro_bridge(stage=stage)

    assert (str(raised.value), [raised.value], runs, active_macro_bridge()) == (
        test_case.expected_error_message,
        raised_errors,
        test_case.expected_bridged_runs,
        None,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
