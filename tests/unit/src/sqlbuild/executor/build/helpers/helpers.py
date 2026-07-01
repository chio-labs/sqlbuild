"""Test helpers for build output formatter tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.node_source_watermarks.main.read import read_latest_node_source_watermarks
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
)
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
    SourceLoadPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.spec.models.schema import SeedCsvSettings
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


@dataclass(frozen=True)
class ModelPlanOverride:
    """Override for a model plan entry in output tests."""

    name: str
    materialization_type: MaterializationType = MaterializationType.TABLE
    action: PlanAction = PlanAction.CREATE_TABLE
    snapshot_strategy: str | None = None
    observed_at_column: str | None = None
    historical_input: str | None = None


def build_model_result_fields(
    *,
    name: str,
    status: ExecutionStatus,
    duration_ms: int = 100,
    failed_phase: ExecutionPhase | None = None,
    staging_relation: str | None = None,
    promoted_relation: str | None = None,
    error_message: str | None = None,
    audit_results: tuple[AuditExecutionResult, ...] = (),
    warning_messages: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "model_name": name,
        "status": status,
        "duration_ms": duration_ms,
        "failed_phase": failed_phase,
        "staging_relation": staging_relation,
        "promoted_relation": promoted_relation,
        "error_message": error_message,
        "audit_results": audit_results,
        "warning_messages": warning_messages,
    }


def build_audit_result(
    *,
    name: str,
    outcome: AuditOutcome,
    row_count: int = 0,
    column_name: str | None = None,
    run_scope_phase: AuditRunScope = AuditRunScope.FINAL,
) -> AuditExecutionResult:
    return AuditExecutionResult(
        audit_name=name,
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.WARN if outcome == AuditOutcome.WARN else AuditSeverity.ERROR,
        outcome=outcome,
        row_count=row_count,
        executed_sql="SELECT 1",
        run_scope_phase=run_scope_phase,
        attached_target_name="test_model",
        attached_column_name=column_name,
    )


def build_model_plan_entry(
    *,
    name: str,
    materialization_type: MaterializationType = MaterializationType.TABLE,
    action: PlanAction = PlanAction.CREATE_TABLE,
    reason: PlanReason = PlanReason.FIRST_RUN,
    resolved_sql: str = "SELECT 1",
    incremental_strategy: str | None = None,
    snapshot_strategy: str | None = None,
    observed_at_column: str | None = None,
    historical_input: str | None = None,
) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=materialization_type,
        action=action,
        reason=reason,
        destination=CompiledRelationLocation(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        fingerprint_query_sql="SELECT 1",
        resolved_sql=resolved_sql,
        logical_ddl=f"CREATE TABLE main.{name} AS SELECT 1",
        incremental_strategy=incremental_strategy,
        snapshot_strategy=snapshot_strategy,
        observed_at_column=observed_at_column,
        historical_input=historical_input,
    )


def build_source_freshness_record(
    *,
    source_name: str,
    data_hash: str,
    data_version: str = "2026-06-30T12:00:00",
) -> SourceFreshnessRecord:
    return SourceFreshnessRecord(
        source_name=source_name,
        target_database=None,
        target_schema="main",
        target_name=source_name,
        run_id="run-1",
        strategy="adapter",
        value_kind="timestamp",
        data_version=data_version,
        data_version_hash=data_hash,
        observed_at=datetime(2026, 6, 30, 12, 1),
    )


def read_node_source_watermark_records(
    *,
    adapter: DuckDbAdapter,
    connection: object,
) -> dict[str, NodeSourceWatermarkRecord]:
    records: dict[NodeSourceWatermarkIdentity, NodeSourceWatermarkRecord] = (
        read_latest_node_source_watermarks(
            connection=connection,
            execute=adapter.execute,
            table_exists=True,
            database=None,
            schema="main",
            render_qualified_name=adapter.render_qualified_name,
            render_read_latest_sql=adapter.render_read_latest_node_source_watermarks_sql,
        ).records
    )
    return {identity.node_name: record for identity, record in records.items()}


def build_seed_plan_entry(*, name: str) -> SeedPlanEntry:
    return SeedPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=name),
        name=name,
        destination=CompiledRelationLocation(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        file_path=Path(f"seeds/{name}.csv"),
        columns=(),
        csv_settings=SeedCsvSettings(),
    )


def build_source_load_plan_output(*, source_name: str, loader_name: str) -> PlanOutput:
    source_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SOURCE,
        name=source_name,
    )
    return PlanOutput(
        source_load_entries=(
            SourceLoadPlanEntry(
                key=source_key,
                name=source_name,
                loader=loader_name,
                destination=source_name,
            ),
        ),
        source_map={
            source_name: SourceEntry(
                name=source_name,
                loader=loader_name,
                write_strategy=SourceWriteStrategy.TABLE,
                columns=(
                    SourceColumnEntry(name="id", type="INTEGER"),
                    SourceColumnEntry(name="status", type="VARCHAR"),
                ),
            )
        },
    )


def source_node_test_loader(_ctx: object) -> list[dict[str, object]]:
    return [{"id": 1, "status": "loaded"}]


def failing_source_node_test_loader(_ctx: object) -> list[dict[str, object]]:
    raise RuntimeError("loader failed intentionally")


def build_discovered_source_loader(*, loader_name: str) -> DiscoveredLoaderFunction:
    return DiscoveredLoaderFunction(
        file_path=Path("loaders/raw.py"),
        relative_path=Path("loaders/raw.py"),
        name=loader_name,
        function=source_node_test_loader,
    )


def build_failing_discovered_source_loader(*, loader_name: str) -> DiscoveredLoaderFunction:
    return DiscoveredLoaderFunction(
        file_path=Path("loaders/raw.py"),
        relative_path=Path("loaders/raw.py"),
        name=loader_name,
        function=failing_source_node_test_loader,
    )


def fetch_rows_or_empty(connection: Any, sql: str) -> tuple[tuple[object, ...], ...]:
    try:
        return tuple(connection.execute(sql).fetchall())
    except Exception:
        return ()


def build_plan_output(
    *,
    model_entries: tuple[ModelPlanEntry, ...] = (),
    seed_entries: tuple[SeedPlanEntry, ...] = (),
) -> PlanOutput:
    return PlanOutput(
        model_entries=model_entries,
        seed_entries=seed_entries,
    )
