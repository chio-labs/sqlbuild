"""Helpers for Python check CLI projection tests."""

from dataclasses import replace

from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult
from sqlbuild.python_nodes.types import PythonCheckSeverity
from sqlbuild.runtime.observability.types import JSONValue
from tests.unit.src.sqlbuild.runtime.observability.helpers import lifecycle_event


def publish_check_attempt(
    *, projector: NativeProgressProjector, name: str, duration_ms: int
) -> None:
    attempt_id: str = f"attempt-{name}"
    payload: dict[str, JSONValue] = {
        "resource_kind": "check",
        "resource_name": name,
        "attempt_number": 1,
    }
    projector.consume(
        replace(
            lifecycle_event(
                "resource_attempt_started",
                run_id="check-run",
                resource_id=f"check:{name}",
                resource_attempt_id=attempt_id,
                payload=payload,
            ),
            event_id=f"start-{name}",
        )
    )
    projector.consume(
        replace(
            lifecycle_event(
                "resource_attempt_completed",
                run_id="check-run",
                resource_id=f"check:{name}",
                resource_attempt_id=attempt_id,
                payload={**payload, "duration_ms": duration_ms},
            ),
            event_id=f"complete-{name}",
        )
    )


def check_results() -> tuple[PythonCheckExecutionResult, ...]:
    return (
        PythonCheckExecutionResult(
            node_name="first", passed=True, severity=PythonCheckSeverity.ERROR
        ),
        PythonCheckExecutionResult(
            node_name="second", passed=True, severity=PythonCheckSeverity.ERROR
        ),
    )
