"""Public Python check runtime target writing entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.target_artifacts._helpers.runtime import (
    write_python_check_runtime_target as _write_python_check_runtime_target,
)
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult


def write_python_check_runtime_target(
    *, target_dir: Path, results: tuple[PythonCheckExecutionResult, ...]
) -> None:
    """Write Python check runtime results under target/run/checks."""

    _write_python_check_runtime_target(target_dir=target_dir, results=results)
