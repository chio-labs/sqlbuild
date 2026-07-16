"""Public SQL test runtime target writing entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.target_artifacts._helpers.runtime import (
    write_test_runtime_target as _write_test_runtime_target,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.testing.models import SqlTestExecutionResult


def write_test_runtime_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
    results: tuple[SqlTestExecutionResult, ...],
) -> None:
    """Write executed SQL unit-test statements under target/run/tests."""

    _write_test_runtime_target(
        target_dir=target_dir,
        adapter=adapter,
        plan_output=plan_output,
        results=results,
    )
