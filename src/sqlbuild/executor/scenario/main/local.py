"""Local scenario replay entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario.helpers.local_snapshots import load_scenario_snapshot_into_duckdb
from sqlbuild.executor.scenario.helpers.snapshots import (
    build_scenario_snapshot_input_fingerprint,
    build_scenario_snapshot_input_specs,
    classify_scenario_snapshot_state,
)
from sqlbuild.executor.scenario.models import ScenarioRunResult, ScenarioSnapshotStateResult
from sqlbuild.executor.scenario.types import ScenarioLocalRunStatus, ScenarioSnapshotState
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.constants import (
    SCENARIO_LOCAL_INTERNAL,
    SCENARIO_LOCAL_MANIFEST_INVALID,
    SCENARIO_LOCAL_SNAPSHOT_MISSING,
    SCENARIO_LOCAL_SNAPSHOT_STALE,
)
from sqlbuild.shared.helpers.coded_errors import error_code, error_help, error_message


def execute_local_scenario_load_only_run(
    *,
    project_dir: Path,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    retain: bool,
    strict: bool,
) -> ScenarioRunResult:
    """Load one local scenario snapshot into a run-scoped DuckDB database."""

    snapshot_state: ScenarioSnapshotStateResult = classify_scenario_snapshot_state(
        project_dir=project_dir,
        scenario_plan=scenario_plan,
    )
    if snapshot_state.state == ScenarioSnapshotState.MISSING:
        return _local_snapshot_unavailable_result(
            scenario_name=scenario_plan.name,
            status=ScenarioLocalRunStatus.ERROR if strict else ScenarioLocalRunStatus.SKIP,
            code=SCENARIO_LOCAL_SNAPSHOT_MISSING,
            message=(
                f"Scenario '{scenario_plan.name}' is missing local snapshot manifest "
                f"'{snapshot_state.manifest_path.as_posix()}'."
            ),
            help=f"Run `sqb scenario capture {scenario_plan.name}` to create the snapshot.",
        )
    if snapshot_state.state == ScenarioSnapshotState.STALE:
        return _local_snapshot_unavailable_result(
            scenario_name=scenario_plan.name,
            status=ScenarioLocalRunStatus.ERROR if strict else ScenarioLocalRunStatus.SKIP,
            code=SCENARIO_LOCAL_SNAPSHOT_STALE,
            message=(
                f"Scenario '{scenario_plan.name}' local snapshot "
                f"'{snapshot_state.manifest_path.as_posix()}' is stale."
            ),
            help=f"Run `sqb scenario capture {scenario_plan.name}` to refresh the snapshot.",
        )
    if snapshot_state.state == ScenarioSnapshotState.INVALID:
        return _local_snapshot_unavailable_result(
            scenario_name=scenario_plan.name,
            status=ScenarioLocalRunStatus.ERROR,
            code=snapshot_state.error_code or SCENARIO_LOCAL_MANIFEST_INVALID,
            message=snapshot_state.error_message
            or (
                f"Scenario '{scenario_plan.name}' has invalid local snapshot manifest "
                f"'{snapshot_state.manifest_path.as_posix()}'."
            ),
            help="Fix scenario.json or regenerate it with `sqb scenario capture`.",
        )

    run_dir: Path = project_dir / "target" / "run" / "scenarios" / scenario_plan.name
    run_dir.mkdir(parents=True, exist_ok=True)
    duckdb_path: Path = run_dir / "local.duckdb"
    _remove_local_duckdb_files(duckdb_path)
    connection: Any = adapter.connect({"database": str(duckdb_path)})
    try:
        input_fingerprint: str = build_scenario_snapshot_input_fingerprint(
            scenario_name=scenario_plan.name,
            input_specs=build_scenario_snapshot_input_specs(scenario_plan=scenario_plan),
        )
        load_scenario_snapshot_into_duckdb(
            project_dir=project_dir,
            scenario_name=scenario_plan.name,
            current_input_fingerprint=input_fingerprint,
            connection=connection,
        )
    except Exception as exc:
        return ScenarioRunResult(
            scenario_name=scenario_plan.name,
            status=ExecutionStatus.FAILED,
            local_status=ScenarioLocalRunStatus.ERROR,
            retained=True,
            local_duckdb_path=duckdb_path,
            error_code=error_code(exc, fallback_code=SCENARIO_LOCAL_INTERNAL),
            error_help=error_help(exc),
            error_message=error_message(exc),
        )
    finally:
        adapter.close(connection)

    if not retain:
        _remove_local_duckdb_files(duckdb_path)
    return ScenarioRunResult(
        scenario_name=scenario_plan.name,
        status=ExecutionStatus.SUCCESS,
        local_status=ScenarioLocalRunStatus.PASS,
        retained=retain,
        local_duckdb_path=duckdb_path if retain else None,
    )


def _local_snapshot_unavailable_result(
    *,
    scenario_name: str,
    status: ScenarioLocalRunStatus,
    code: str,
    message: str,
    help: str,
) -> ScenarioRunResult:
    return ScenarioRunResult(
        scenario_name=scenario_name,
        status=ExecutionStatus.SKIPPED
        if status == ScenarioLocalRunStatus.SKIP
        else ExecutionStatus.FAILED,
        local_status=status,
        retained=False,
        error_code=code,
        error_help=help,
        error_message=message,
    )


def _remove_local_duckdb_files(duckdb_path: Path) -> None:
    duckdb_path.unlink(missing_ok=True)
    duckdb_path.with_name(f"{duckdb_path.name}.wal").unlink(missing_ok=True)
