"""Public scenario snapshot execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_result_document import (
    format_scenario_snapshot_execution_json as _format_scenario_snapshot_execution_json,
)
from sqlbuild.executor.scenario.models import ScenarioSnapshotCaptureRunResult


def format_scenario_snapshot_execution_json(
    *,
    results: tuple[ScenarioSnapshotCaptureRunResult, ...],
    refresh: bool = False,
    run_namespace: str | None = None,
    namespace_source: str = "unset",
) -> str:
    """Format scenario snapshot sync/refresh execution results as JSON."""

    return _format_scenario_snapshot_execution_json(
        results=results,
        refresh=refresh,
        run_namespace=run_namespace,
        namespace_source=namespace_source,
    )
