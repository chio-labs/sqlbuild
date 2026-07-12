"""Public runtime target writing entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.target_artifacts.helpers.runtime import (
    write_runtime_target as _write_runtime_target,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult


def write_runtime_target(
    *, target_dir: Path, plan_output: PlanOutput, result: BuildExecutionResult
) -> None:
    """Write executed model lifecycle SQL under target/run."""

    _write_runtime_target(target_dir=target_dir, plan_output=plan_output, result=result)
