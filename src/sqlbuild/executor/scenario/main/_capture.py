"""Capture materialized scenario input relations into local snapshot files."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.errors.contracts.main.error_code import error_code
from sqlbuild.executor.scenario._helpers.capture.relation import (
    capture_scenario_snapshot_relation,
    scenario_capture_source_relation_name,
)
from sqlbuild.executor.scenario._helpers.capture.safety import capture_error_help
from sqlbuild.executor.scenario._helpers.snapshots.core import (
    write_scenario_snapshot_manifest,
)
from sqlbuild.executor.scenario.constants import SCENARIO_EXEC_CAPTURE_FAILED
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCapturePlan,
    ScenarioSnapshotCaptureRelationPlan,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureResult,
    ScenarioSnapshotManifest,
    ScenarioSnapshotRelation,
)
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


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
            result, manifest_relation, preflight_row_count = capture_scenario_snapshot_relation(
                capture_plan=capture_plan,
                relation_plan=relation_plan,
                adapter=adapter,
                connection=connection,
                local_type_overrides=local_type_overrides,
                limits=effective_limits,
                total_row_count=total_row_count,
                total_byte_count=total_byte_count,
            )
            total_row_count += preflight_row_count
            total_byte_count += result.byte_count
            manifest_relations.append(manifest_relation)
        except Exception as exc:
            captured_error_code: str = error_code(
                error=exc,
                fallback_code=SCENARIO_EXEC_CAPTURE_FAILED,
            )
            result = ScenarioSnapshotCaptureRelationResult(
                kind=relation_plan.kind,
                logical_name=relation_plan.logical_name,
                source_relation=scenario_capture_source_relation_name(
                    adapter=adapter, relation_plan=relation_plan
                ),
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
    with OperationLifecycle(
        operation_kind="scenario", operation_name="scenario_snapshot_serialization"
    ) as serialization:
        write_scenario_snapshot_manifest(
            manifest_path=capture_plan.manifest_path,
            manifest=final_manifest,
        )
        serialization.completed(
            metadata={
                "item_count": len(final_manifest.relations),
                "row_count": final_manifest.total_rows,
                "byte_count": final_manifest.total_bytes,
            }
        )
    return ScenarioSnapshotCaptureResult(
        scenario_name=capture_plan.scenario_name,
        status=ExecutionStatus.SUCCESS,
        manifest_path=capture_plan.manifest_path,
        manifest=final_manifest,
        relation_results=tuple(relation_results),
    )
