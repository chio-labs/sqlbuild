"""Direct build source freshness state helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_record
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
    StandardSourceFreshnessPlanningResult,
)
from sqlbuild.executor.build.models import BuildExecutionResult


def append_eligible_standard_source_freshness_records(
    *,
    plan: PlanOutput,
    result: BuildExecutionResult,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    run_id: str,
) -> None:
    """Append observed source freshness only after affected selected models succeed."""

    source_freshness: StandardSourceFreshnessPlanningResult | None = plan.source_freshness
    if source_freshness is None or source_freshness.propagation is None:
        return

    selected_model_names: frozenset[str] = frozenset(entry.name for entry in plan.model_entries)
    if not selected_model_names:
        return

    successful_model_names: frozenset[str] = frozenset(
        model_result.model_name
        for model_result in result.model_results
        if getattr(model_result.status, "value", model_result.status) == "success"
    )
    observed_records_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {
        record.identity: record for record in source_freshness.observed_records
    }
    entries_by_name: dict[str, ModelPlanEntry] = {entry.name: entry for entry in plan.model_entries}

    connection: Any = adapter.connect(connection_config)
    try:
        identity: SourceFreshnessIdentity
        affected_model_names: frozenset[str]
        for (
            identity,
            affected_model_names,
        ) in source_freshness.propagation.changed_source_model_names.items():
            affected_selected_model_names: frozenset[str] = (
                affected_model_names & selected_model_names
            )
            if not affected_selected_model_names:
                continue
            if not affected_selected_model_names <= successful_model_names:
                continue
            record: SourceFreshnessRecord | None = observed_records_by_identity.get(identity)
            if record is None:
                continue
            _append_record_to_affected_model_schemas(
                adapter=adapter,
                connection=connection,
                record=replace(record, run_id=run_id),
                affected_model_names=affected_selected_model_names,
                entries_by_name=entries_by_name,
            )
    finally:
        adapter.close(connection)


def _append_record_to_affected_model_schemas(
    *,
    adapter: BaseAdapter,
    connection: Any,
    record: SourceFreshnessRecord,
    affected_model_names: frozenset[str],
    entries_by_name: dict[str, ModelPlanEntry],
) -> None:
    written_locations: set[tuple[str | None, str]] = set()
    model_name: str
    for model_name in sorted(affected_model_names):
        entry: ModelPlanEntry | None = entries_by_name.get(model_name)
        if entry is None or entry.destination.schema is None:
            continue
        location: tuple[str | None, str] = (entry.destination.database, entry.destination.schema)
        if location in written_locations:
            continue
        written_locations.add(location)
        write_source_freshness_record(
            connection=connection,
            execute=adapter.execute,
            database=entry.destination.database,
            schema=entry.destination.schema,
            record=record,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        )
