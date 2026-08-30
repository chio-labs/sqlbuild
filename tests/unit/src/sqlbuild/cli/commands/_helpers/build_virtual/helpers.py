from __future__ import annotations

from io import StringIO
from typing import cast
from unittest.mock import Mock

import pytest

from sqlbuild.cli.commands._helpers.build_virtual import virtual_execution
from sqlbuild.cli.commands.classes.build_progress_callbacks import BuildProgressCallbacks
from sqlbuild.cli.commands.classes.virtual_build_plan_hook import VirtualBuildPlanHook
from sqlbuild.cli.commands.models import VirtualBuildCliRequest, VirtualBuildExecution
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.cost.models import StatementExecutionTelemetry
from sqlbuild.executor.build.models import SchedulerState


class _TrackingBuildProgressCallbacks(BuildProgressCallbacks):
    def __init__(self) -> None:
        super().__init__(plan=PlanOutput(), use_color=False, verbose=True)
        self.close_calls: int = 0

    def close(self) -> None:
        self.close_calls += 1
        super().close()


def build_high_volume_virtual_hook() -> tuple[
    VirtualBuildPlanHook, _TrackingBuildProgressCallbacks
]:
    callbacks: _TrackingBuildProgressCallbacks = _TrackingBuildProgressCallbacks()
    hook: VirtualBuildPlanHook = object.__new__(VirtualBuildPlanHook)
    hook.callbacks = callbacks
    hook._closed = False
    return hook, callbacks


def emit_high_volume_virtual_diagnostics(hook: VirtualBuildPlanHook) -> None:
    callbacks: BuildProgressCallbacks = cast(BuildProgressCallbacks, hook.callbacks)
    for index in range(52):
        callbacks.on_scheduler_state(SchedulerState(running=1, ready=0, waiting=index, limit=4))
    for index in range(27):
        callbacks.on_statement_complete(
            StatementExecutionTelemetry(
                query_id=f"virtual-query-{index}",
                status="success",
                elapsed_seconds=0.1,
                resource_type="model",
                resource_name="orders",
                phase="microbatch",
            )
        )


def patch_virtual_execution(
    *,
    monkeypatch: pytest.MonkeyPatch,
    hook: VirtualBuildPlanHook,
    pipeline: Mock,
) -> None:
    monkeypatch.setattr(virtual_execution, "VirtualBuildPlanHook", Mock(return_value=hook))
    monkeypatch.setattr(virtual_execution, "ConnectionProgressReporter", Mock())
    monkeypatch.setattr(virtual_execution, "PlanningProgressReporter", Mock())
    monkeypatch.setattr(virtual_execution, "resolve_target_name", Mock(return_value=None))
    monkeypatch.setattr(virtual_execution, "run_virtual_build_pipeline", pipeline)


def execute_patched_virtual_build() -> VirtualBuildExecution:
    discovered_inputs: Mock = Mock()
    discovered_inputs.project_config.snapshots = None
    return virtual_execution.execute_virtual_build(
        project_dir=Mock(),
        discovered_inputs=discovered_inputs,
        adapter=Mock(),
        adapter_name="test",
        connection_config={},
        request=VirtualBuildCliRequest(verbose=True),
        progress_stream=StringIO(),
    )
