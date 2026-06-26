"""Source freshness command state helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.compiler.source_freshness.main.read import read_latest_source_freshness
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord
from sqlbuild.spec.models.targets import resolve_target_name
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import SourceFreshnessRecord as VirtualSourceFreshnessRecord


def read_standard_freshness_state_for_command(
    *, adapter: StrictAdapter, connection: Any, project: Any
) -> dict[SourceFreshnessIdentity, SourceFreshnessRecord]:
    """Read standard source freshness state for all compiled target schemas."""

    records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {}
    state_database: str | None = _resolve_state_database(project=project)
    state_schema: str
    for state_schema in _collect_state_schemas(project=project):
        records.update(
            read_latest_source_freshness(
                connection=connection,
                execute=adapter.execute,
                table_exists=adapter.relation_exists(
                    connection,
                    database=state_database,
                    schema=state_schema,
                    name=SOURCE_FRESHNESS_TABLE_NAME,
                ),
                database=state_database,
                schema=state_schema,
                render_qualified_name=adapter.render_qualified_name,
                render_read_latest_sql=adapter.render_read_latest_source_freshness_sql,
            ).records
        )
    return records


def read_virtual_freshness_state_for_command(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Any,
    virtual_environment_name: str | None,
) -> dict[str, SourceFreshnessRecord]:
    """Read virtual source freshness state by source name for one virtual environment."""

    config: Any
    backend: Any
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    try:
        target_name: str | None = virtual_environment_name or resolve_target_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            selected_target=None,
        )
        if target_name is None:
            return {}
        records: tuple[VirtualSourceFreshnessRecord, ...] = (
            backend.get_virtual_environment_source_freshness(
                state_connection,
                schema=config.schema,
                virtual_environment_name=target_name,
            )
        )
        return {
            record.source_name: _standard_record_from_virtual_record(record) for record in records
        }
    finally:
        backend.close(state_connection)


def _standard_record_from_virtual_record(
    record: VirtualSourceFreshnessRecord,
) -> SourceFreshnessRecord:
    return SourceFreshnessRecord(
        source_name=record.source_name,
        target_database=None,
        target_schema=None,
        target_name=None,
        run_id=record.virtual_environment_name,
        strategy=record.strategy,
        value_kind=record.value_kind,
        data_version=record.data_version,
        data_version_hash=record.data_version_hash,
        observed_at=record.observed_at,
    )


def _resolve_state_database(*, project: Any) -> str | None:
    destination: Any
    for destination in _iter_state_destinations(project=project):
        if destination.database is not None:
            return destination.database
    return None


def _collect_state_schemas(*, project: Any) -> tuple[str, ...]:
    schemas: set[str] = set()
    destination: Any
    for destination in _iter_state_destinations(project=project):
        if destination.schema is not None:
            schemas.add(destination.schema)
    return tuple(sorted(schemas))


def _iter_state_destinations(*, project: Any) -> tuple[Any, ...]:
    return (
        *(model.destination for model in project.models),
        *(seed.destination for seed in project.seeds),
        *(function.destination for function in project.functions),
    )
