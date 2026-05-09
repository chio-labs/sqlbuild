"""Capture materialized scenario input relations into local snapshot files."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import QueryResult
from sqlbuild.executor.scenario.helpers.snapshots import (
    write_scenario_snapshot_jsonl,
    write_scenario_snapshot_manifest,
)
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCapturePlan,
    ScenarioSnapshotCaptureRelationPlan,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureResult,
    ScenarioSnapshotFileStats,
    ScenarioSnapshotManifest,
    ScenarioSnapshotRelation,
)
from sqlbuild.executor.shared.types import ExecutionStatus


def execute_scenario_snapshot_capture(
    *,
    capture_plan: ScenarioSnapshotCapturePlan,
    manifest: ScenarioSnapshotManifest,
    adapter: BaseAdapter,
    connection: Any,
) -> ScenarioSnapshotCaptureResult:
    """Write JSONL relation snapshots and a final manifest from materialized inputs."""

    relation_results: list[ScenarioSnapshotCaptureRelationResult] = []
    manifest_relations: list[ScenarioSnapshotRelation] = []
    relation_plan: ScenarioSnapshotCaptureRelationPlan
    for relation_plan in capture_plan.relations:
        result: ScenarioSnapshotCaptureRelationResult
        try:
            rows: tuple[dict[str, object], ...] = _query_relation_rows(
                adapter=adapter,
                connection=connection,
                relation_plan=relation_plan,
            )
            stats: ScenarioSnapshotFileStats = write_scenario_snapshot_jsonl(
                file_path=capture_plan.snapshot_root / relation_plan.file_path,
                rows=rows,
            )
            result = ScenarioSnapshotCaptureRelationResult(
                kind=relation_plan.kind,
                logical_name=relation_plan.logical_name,
                source_relation=_source_relation_name(relation_plan),
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
                )
            )
        except Exception as exc:
            result = ScenarioSnapshotCaptureRelationResult(
                kind=relation_plan.kind,
                logical_name=relation_plan.logical_name,
                source_relation=_source_relation_name(relation_plan),
                file_path=relation_plan.file_path,
                status=ExecutionStatus.FAILED,
                error_message=f"Failed to capture {relation_plan.kind.value} "
                f"'{relation_plan.logical_name}': {exc}",
            )
            relation_results.append(result)
            return ScenarioSnapshotCaptureResult(
                scenario_name=capture_plan.scenario_name,
                status=ExecutionStatus.FAILED,
                manifest_path=capture_plan.manifest_path,
                relation_results=tuple(relation_results),
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
        f"SELECT * FROM {_source_relation_name(relation_plan)}",
        limit=None,
    )
    rows: list[dict[str, object]] = []
    row: tuple[object, ...]
    for row in query_result.rows:
        if len(row) != len(query_result.columns):
            raise ValueError(
                "row value count does not match column count for relation "
                f"'{relation_plan.logical_name}'"
            )
        rows.append(dict(zip(query_result.columns, row, strict=True)))
    return tuple(rows)


def _source_relation_name(relation_plan: ScenarioSnapshotCaptureRelationPlan) -> str:
    qualified_name: str | None = relation_plan.source_target.qualified_name
    if qualified_name is None:
        raise ValueError(
            f"Scenario snapshot relation '{relation_plan.logical_name}' has no qualified target"
        )
    return qualified_name
