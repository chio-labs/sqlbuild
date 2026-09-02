"""Direct build source freshness state helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_records
from sqlbuild.compiler.source_freshness.models import (
    DirectSourceFreshnessPlanningResult,
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
    SourceFreshnessRenderers,
)
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.observability import run_scope
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.runtime.observability.models import OperationAttributes


def append_eligible_direct_source_freshness_records(
    *,
    plan: PlanOutput,
    result: BuildExecutionResult,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    run_id: str,
) -> None:
    """Append observed source freshness only after affected selected models succeed."""

    source_freshness: DirectSourceFreshnessPlanningResult | None = plan.source_freshness
    if source_freshness is None or source_freshness.propagation is None:
        return

    selected_model_names: frozenset[str] = frozenset(entry.name for entry in plan.model_entries)
    if not selected_model_names:
        return

    successful_model_names: frozenset[str] = frozenset(
        model_result.model_name
        for model_result in result.model_results
        if getattr(model_result.status, "value", model_result.status) == ExecutionStatus.SUCCESS
    )
    observed_records_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {
        record.identity: record for record in source_freshness.observed_records
    }
    entries_by_name: dict[str, ModelPlanEntry] = {entry.name: entry for entry in plan.model_entries}

    records_by_location: dict[tuple[str | None, str], list[SourceFreshnessRecord]] = {}
    identity: SourceFreshnessIdentity
    affected_model_names: frozenset[str]
    for (
        identity,
        affected_model_names,
    ) in source_freshness.propagation.changed_source_model_names.items():
        affected_selected_model_names: frozenset[str] = affected_model_names & selected_model_names
        if not affected_selected_model_names:
            continue
        if not affected_selected_model_names <= successful_model_names:
            continue
        record: SourceFreshnessRecord | None = observed_records_by_identity.get(identity)
        if record is None:
            continue
        records_by_location = _collect_record_for_affected_model_schemas(
            records_by_location=records_by_location,
            record=replace(record, run_id=run_id),
            affected_model_names=affected_selected_model_names,
            entries_by_name=entries_by_name,
        )
    record_count: int = sum(len(records) for records in records_by_location.values())
    if record_count == 0:
        return
    with run_scope(run_id):
        with OperationLifecycle(
            operation_kind="freshness",
            operation_name="source_freshness_publication",
            metadata={"item_count": record_count},
            attributes=OperationAttributes(phase="publish", target_kind="state_batch"),
        ):
            connection: Any = adapter.connect(connection_config)
            try:
                _append_records_by_location(
                    adapter=adapter,
                    connection=connection,
                    records_by_location=records_by_location,
                )
            finally:
                adapter.close(connection)


def _collect_record_for_affected_model_schemas(
    *,
    records_by_location: dict[tuple[str | None, str], list[SourceFreshnessRecord]],
    record: SourceFreshnessRecord,
    affected_model_names: frozenset[str],
    entries_by_name: dict[str, ModelPlanEntry],
) -> dict[tuple[str | None, str], list[SourceFreshnessRecord]]:
    recorded_locations: set[tuple[str | None, str]] = set()
    model_name: str
    for model_name in sorted(affected_model_names):
        entry: ModelPlanEntry | None = entries_by_name.get(model_name)
        if entry is None or entry.destination.schema is None:
            continue
        location: tuple[str | None, str] = (entry.destination.database, entry.destination.schema)
        if location in recorded_locations:
            continue
        recorded_locations.add(location)
        records_by_location.setdefault(location, []).append(record)
    return records_by_location


def _append_records_by_location(
    *,
    adapter: BaseAdapter,
    connection: Any,
    records_by_location: dict[tuple[str | None, str], list[SourceFreshnessRecord]],
) -> None:
    location: tuple[str | None, str]
    records: list[SourceFreshnessRecord]
    for location, records in records_by_location.items():
        database, schema = location
        records_by_source_name: dict[str, list[SourceFreshnessRecord]] = {}
        record: SourceFreshnessRecord
        for record in records:
            records_by_source_name.setdefault(record.source_name, []).append(record)
        source_name: str
        source_records: list[SourceFreshnessRecord]
        for source_name, source_records in records_by_source_name.items():
            with CostContext.resource_scope(
                resource_type="source",
                resource_name=source_name,
                phase="freshness_finalization",
            ):
                write_source_freshness_records(
                    connection=connection,
                    execute=adapter.execute,
                    database=database,
                    schema=schema,
                    records=tuple(source_records),
                    renderers=SourceFreshnessRenderers(
                        render_qualified_name=adapter.render_qualified_name,
                        render_framework_type=adapter.render_framework_type,
                        render_insert_records_sql=adapter.render_insert_source_freshness_records_sql,
                        render_create_index_sqls=adapter.render_create_source_freshness_index_sqls,
                    ),
                    transient=adapter.state_tables_transient,
                )
