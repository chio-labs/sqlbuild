"""One scenario snapshot relation capture boundary."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import QueryResult
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.executor.scenario._helpers.capture.columns import build_scenario_snapshot_columns
from sqlbuild.executor.scenario._helpers.capture.safety import (
    max_relation_write_bytes,
    query_capture_relation_row_count,
    validate_capture_row_limits,
)
from sqlbuild.executor.scenario._helpers.snapshots.core import write_scenario_snapshot_jsonl
from sqlbuild.executor.scenario.constants import SCENARIO_EXEC_CAPTURE_INTERNAL
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCapturePlan,
    ScenarioSnapshotCaptureRelationPlan,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotColumn,
    ScenarioSnapshotFileStats,
    ScenarioSnapshotRelation,
)
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def capture_scenario_snapshot_relation(
    *,
    capture_plan: ScenarioSnapshotCapturePlan,
    relation_plan: ScenarioSnapshotCaptureRelationPlan,
    adapter: BaseAdapter,
    connection: Any,
    local_type_overrides: dict[str, str] | None,
    limits: ScenarioSnapshotCaptureLimits,
    total_row_count: int,
    total_byte_count: int,
) -> tuple[ScenarioSnapshotCaptureRelationResult, ScenarioSnapshotRelation, int]:
    """Read, inspect, and serialize one independently actionable relation."""

    source_relation_name: str = scenario_capture_source_relation_name(
        adapter=adapter, relation_plan=relation_plan
    )
    with OperationLifecycle(
        operation_kind="scenario", operation_name="scenario_relation_read"
    ) as relation_read:
        preflight_row_count: int = query_capture_relation_row_count(
            adapter=adapter,
            connection=connection,
            relation_plan=relation_plan,
            source_relation_name=source_relation_name,
        )
        if not limits.force:
            validate_capture_row_limits(
                scenario_name=capture_plan.scenario_name,
                relation_plan=relation_plan,
                relation_row_count=preflight_row_count,
                total_row_count=total_row_count,
                limits=limits,
            )
        rows: tuple[dict[str, object], ...] = _query_relation_rows(
            adapter=adapter,
            connection=connection,
            relation_plan=relation_plan,
        )
        relation_read.completed(metadata={"row_count": len(rows)})
    with OperationLifecycle(
        operation_kind="scenario", operation_name="scenario_schema_inspection"
    ) as schema_inspection:
        columns: tuple[ScenarioSnapshotColumn, ...] = build_scenario_snapshot_columns(
            adapter=adapter,
            connection=connection,
            relation_name=source_relation_name,
            local_type_overrides=local_type_overrides,
        )
        schema_inspection.completed(metadata={"item_count": len(columns)})
    with OperationLifecycle(
        operation_kind="scenario", operation_name="scenario_snapshot_write"
    ) as snapshot_write:
        stats: ScenarioSnapshotFileStats = write_scenario_snapshot_jsonl(
            file_path=capture_plan.snapshot_root / relation_plan.file_path,
            rows=rows,
            max_bytes=max_relation_write_bytes(
                total_byte_count=total_byte_count,
                limits=limits,
            ),
        )
        snapshot_write.completed(
            metadata={"row_count": stats.row_count, "byte_count": stats.byte_count}
        )
    result: ScenarioSnapshotCaptureRelationResult = ScenarioSnapshotCaptureRelationResult(
        kind=relation_plan.kind,
        logical_name=relation_plan.logical_name,
        source_relation=source_relation_name,
        file_path=relation_plan.file_path,
        status=ExecutionStatus.SUCCESS,
        row_count=stats.row_count,
        byte_count=stats.byte_count,
    )
    return (
        result,
        ScenarioSnapshotRelation(
            kind=relation_plan.kind,
            logical_name=relation_plan.logical_name,
            file_path=relation_plan.file_path,
            row_count=stats.row_count,
            byte_count=stats.byte_count,
            columns=columns,
        ),
        preflight_row_count,
    )


def scenario_capture_source_relation_name(
    *, adapter: BaseAdapter, relation_plan: ScenarioSnapshotCaptureRelationPlan
) -> str:
    """Resolve the warehouse relation used by one capture plan item."""

    return resolve_qualified_name_parts(
        adapter=adapter,
        database=relation_plan.source_target.database,
        schema=relation_plan.source_target.schema,
        name=relation_plan.source_target.name,
    )


def _query_relation_rows(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relation_plan: ScenarioSnapshotCaptureRelationPlan,
) -> tuple[dict[str, object], ...]:
    query_result: QueryResult = adapter.query(
        connection=connection,
        sql=(
            "SELECT * FROM "
            + scenario_capture_source_relation_name(adapter=adapter, relation_plan=relation_plan)
        ),
        limit=None,
    )
    rows: list[dict[str, object]] = []
    row: tuple[object, ...]
    for row in query_result.rows:
        if len(row) != len(query_result.columns):
            error: ValueError = ValueError(
                "row value count does not match column count for relation "
                f"'{relation_plan.logical_name}'"
            )
            object.__setattr__(error, "code", SCENARIO_EXEC_CAPTURE_INTERNAL)
            raise error
        rows.append(dict(zip(query_result.columns, row, strict=True)))
    return tuple(rows)
