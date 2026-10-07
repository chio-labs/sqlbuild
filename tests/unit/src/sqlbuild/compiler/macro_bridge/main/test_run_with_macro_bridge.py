from __future__ import annotations

from collections.abc import Callable

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.frontier.exceptions import NativeStageMismatchError
from sqlbuild.compiler.macro_bridge.main.active_macro_bridge import active_macro_bridge
from sqlbuild.compiler.macro_bridge.main.run_with_macro_bridge import run_with_macro_bridge
from tests.unit.src.sqlbuild.compiler.macro_bridge.main._test_types import (
    MacroBridgeErrorContextTestCase,
    MacroBridgeFailureTestCase,
    MacroBridgeSuccessTestCase,
)
from tests.unit.src.sqlbuild.compiler.macro_bridge.main.helpers import (
    failed,
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

    result: str = run_with_macro_bridge(
        stage=recording_stage(runs=runs, stages={True: rendered, False: failed})
    )

    assert result == test_case.expected_result
    assert runs == test_case.expected_bridged_runs
    assert active_macro_bridge() is None


@pytest.mark.parametrize(
    "test_case",
    [
        MacroBridgeFailureTestCase(
            description="failure re-runs Python and raises its error",
            stage_with_bridge=failed,
            stage_without_bridge=failed,
            expected_error=CompileInputError,
            expected_bridged_runs=[True, False],
        ),
        MacroBridgeFailureTestCase(
            description="native-only failure is reported as a divergence",
            stage_with_bridge=failed,
            stage_without_bridge=rendered,
            expected_error=NativeStageMismatchError,
            expected_bridged_runs=[True, False],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_stage_when_running_with_macro_bridge_then_python_reruns(
    test_case: MacroBridgeFailureTestCase,
) -> None:
    runs: list[bool] = []
    stage: Callable[[], str] = recording_stage(
        runs=runs,
        stages={True: test_case.stage_with_bridge, False: test_case.stage_without_bridge},
    )

    with pytest.raises(test_case.expected_error):
        _ = run_with_macro_bridge(stage=stage)

    assert runs == test_case.expected_bridged_runs
    assert active_macro_bridge() is None


@pytest.mark.parametrize(
    "test_case",
    [
        MacroBridgeErrorContextTestCase(
            description="python error after a bridge failure",
            stage=failed,
            expected_context=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_python_error_when_rerun_after_bridge_failure_then_error_has_no_bridge_context(
    test_case: MacroBridgeErrorContextTestCase,
) -> None:
    with pytest.raises(CompileInputError) as raised:
        _ = run_with_macro_bridge(stage=test_case.stage)

    assert raised.value.__context__ is test_case.expected_context


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
