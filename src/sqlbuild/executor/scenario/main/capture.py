"""Capture materialized scenario input relations into local snapshot files."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import QueryResult
from sqlbuild.executor.scenario.helpers.capture.columns import build_scenario_snapshot_columns
from sqlbuild.executor.scenario.helpers.capture.safety import (
    capture_error_help,
    max_relation_write_bytes,
    query_capture_relation_row_count,
    validate_capture_row_limits,
)
from sqlbuild.executor.scenario.helpers.snapshots.core import (
    write_scenario_snapshot_jsonl,
    write_scenario_snapshot_manifest,
)
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCapturePlan,
    ScenarioSnapshotCaptureRelationPlan,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureResult,
    ScenarioSnapshotColumn,
    ScenarioSnapshotFileStats,
    ScenarioSnapshotManifest,
    ScenarioSnapshotRelation,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.constants import (
    SCENARIO_EXEC_CAPTURE_FAILED,
    SCENARIO_EXEC_CAPTURE_INTERNAL,
)
from sqlbuild.shared.helpers.identity.naming import resolve_qualified_name_parts
from sqlbuild.shared.main.error_code import error_code


def execute_scenario_snapshot_capture(
    *,
    capture_plan: ScenarioSnapshotCapturePlan,
    manifest: ScenarioSnapshotManifest,
    adapter: BaseAdapter,
    connection: Any,
    local_type_overrides: dict[str, str] | None = None,
    limits: ScenarioSnapshotCaptureLimits | None = None,
) -> ScenarioSnapshotCaptureResult:
    """Write JSONL relation snapshots and a final manifest from materialized inputs."""

    relation_results: list[ScenarioSnapshotCaptureRelationResult] = []
    manifest_relations: list[ScenarioSnapshotRelation] = []
    effective_limits: ScenarioSnapshotCaptureLimits = limits or ScenarioSnapshotCaptureLimits()
    total_row_count: int = 0
    total_byte_count: int = 0
    relation_plan: ScenarioSnapshotCaptureRelationPlan
    for relation_plan in capture_plan.relations:
        result: ScenarioSnapshotCaptureRelationResult
        try:
            source_relation_name: str = _source_relation_name(
                adapter=adapter,
                relation_plan=relation_plan,
            )
            preflight_row_count: int = query_capture_relation_row_count(
                adapter=adapter,
                connection=connection,
                relation_plan=relation_plan,
                source_relation_name=source_relation_name,
            )
            if not effective_limits.force:
                validate_capture_row_limits(
                    scenario_name=capture_plan.scenario_name,
                    relation_plan=relation_plan,
                    relation_row_count=preflight_row_count,
                    total_row_count=total_row_count,
                    limits=effective_limits,
                )
            rows: tuple[dict[str, object], ...] = _query_relation_rows(
                adapter=adapter,
                connection=connection,
                relation_plan=relation_plan,
            )
            columns: tuple[ScenarioSnapshotColumn, ...] = build_scenario_snapshot_columns(
                adapter=adapter,
                connection=connection,
                relation_name=_source_relation_name(adapter=adapter, relation_plan=relation_plan),
                local_type_overrides=local_type_overrides,
            )
            stats: ScenarioSnapshotFileStats = write_scenario_snapshot_jsonl(
                file_path=capture_plan.snapshot_root / relation_plan.file_path,
                rows=rows,
                max_bytes=max_relation_write_bytes(
                    total_byte_count=total_byte_count,
                    limits=effective_limits,
                ),
            )
            total_row_count += preflight_row_count
            total_byte_count += stats.byte_count
            result = ScenarioSnapshotCaptureRelationResult(
                kind=relation_plan.kind,
                logical_name=relation_plan.logical_name,
                source_relation=_source_relation_name(adapter=adapter, relation_plan=relation_plan),
                file_path=relation_plan.file_path,
                status=ExecutionStatus.SUCCESS,
                row_count=stats.row_count,
                byte_count=stats.byte_count,
            )
            manifest_relations.append(
                ScenarioSnapshotRelation(
                    kind=relation_plan.kind,
                    logical_name=relation_plan.logical_name,
                    file_path=relation_plan.file_path,
                    row_count=stats.row_count,
                    byte_count=stats.byte_count,
                    columns=columns,
                )
            )
        except Exception as exc:
            captured_error_code: str = error_code(
                exc,
                fallback_code=SCENARIO_EXEC_CAPTURE_FAILED,
            )
            result = ScenarioSnapshotCaptureRelationResult(
                kind=relation_plan.kind,
                logical_name=relation_plan.logical_name,
                source_relation=_source_relation_name(adapter=adapter, relation_plan=relation_plan),
                file_path=relation_plan.file_path,
                status=ExecutionStatus.FAILED,
                error_code=captured_error_code,
                error_help=capture_error_help(captured_error_code),
                error_message=f"Failed to capture {relation_plan.kind.value} "
                f"'{relation_plan.logical_name}': {exc}",
            )
            relation_results.append(result)
            return ScenarioSnapshotCaptureResult(
                scenario_name=capture_plan.scenario_name,
                status=ExecutionStatus.FAILED,
                manifest_path=capture_plan.manifest_path,
                relation_results=tuple(relation_results),
                error_code=captured_error_code,
                error_help=result.error_help,
                error_message=result.error_message,
            )
        relation_results.append(result)

    final_manifest: ScenarioSnapshotManifest = ScenarioSnapshotManifest(
        version=manifest.version,
        scenario_name=manifest.scenario_name,
        captured_at=manifest.captured_at,
        capture_adapter=manifest.capture_adapter,
        capture_dialect=manifest.capture_dialect,
        sqlbuild_version=manifest.sqlbuild_version,
        input_fingerprint=manifest.input_fingerprint,
        total_rows=sum(relation.row_count for relation in manifest_relations),
        total_bytes=sum(relation.byte_count for relation in manifest_relations),
        relations=tuple(manifest_relations),
        format=manifest.format,
    )
    write_scenario_snapshot_manifest(
        manifest_path=capture_plan.manifest_path,
        manifest=final_manifest,
    )
    return ScenarioSnapshotCaptureResult(
        scenario_name=capture_plan.scenario_name,
        status=ExecutionStatus.SUCCESS,
        manifest_path=capture_plan.manifest_path,
        manifest=final_manifest,
        relation_results=tuple(relation_results),
    )


def _query_relation_rows(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relation_plan: ScenarioSnapshotCaptureRelationPlan,
) -> tuple[dict[str, object], ...]:
    query_result: QueryResult = adapter.query(
        connection,
        sql=f"SELECT * FROM {_source_relation_name(adapter=adapter, relation_plan=relation_plan)}",
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


def _source_relation_name(
    *, adapter: BaseAdapter, relation_plan: ScenarioSnapshotCaptureRelationPlan
) -> str:
    return resolve_qualified_name_parts(
        adapter=adapter,
        database=relation_plan.source_target.database,
        schema=relation_plan.source_target.schema,
        name=relation_plan.source_target.name,
    )
