"""Build Python-node result output."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.shared.helpers.output.cli_style import CliStyle


def write_python_node_results(
    *, stream: TextIO, results: tuple[PythonNodeExecutionResult, ...], use_color: bool
) -> None:
    """Write human-readable task and asset execution rows."""

    style: CliStyle = CliStyle(use_color=use_color)
    result: PythonNodeExecutionResult
    for result in results:
        status_text: str = python_node_status_text(result.status)
        stream.write(
            f"  {'python':<10}{result.kind.value:<10}{result.node_name:<50} "
            f"{style.status(status=status_text)}"
        )
        if result.error_message:
            stream.write(f"  {result.error_message}")
        elif result.skip_reason:
            stream.write(f"  {result.skip_reason}")
        stream.write("\n")
    stream.flush()


def python_node_status_text(status: PythonNodeStatus) -> str:
    """Return the short human status label for a Python-node status."""

    if status == PythonNodeStatus.SUCCESS:
        return "OK"
    if status == PythonNodeStatus.SKIPPED:
        return "SKIP"
    return "FAIL"


def python_node_results_failed(results: tuple[PythonNodeExecutionResult, ...]) -> bool:
    """Return whether any Python-node result failed."""

    return any(result.status == PythonNodeStatus.FAILED for result in results)
