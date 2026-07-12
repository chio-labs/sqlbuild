"""Virtual source freshness runtime observation helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.exceptions import AdapterUserError
from sqlbuild.compiler.source_freshness.main.record_equivalence import (
    source_freshness_records_equivalent,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessObservation
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from sqlbuild.virtual.freshness.main.data_version_hash import source_freshness_data_version_hash
from sqlbuild.virtual.freshness.main.observation import observe_configured_source_freshness
from sqlbuild.virtual.freshness.main.state_record import source_freshness_record_from_observation
from sqlbuild.virtual.freshness.models import SourceFreshnessRuntimeResult
from sqlbuild.virtual.state.models import SourceFreshnessRecord


def observe_virtual_environment_source_freshness(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    virtual_environment_name: str,
    observed_at: datetime,
    run_id: str | None = None,
    load_results: tuple[Any, ...] = (),
    previous_records: tuple[SourceFreshnessRecord, ...] = (),
) -> SourceFreshnessRuntimeResult:
    """Observe current source freshness records without using them for skip decisions."""

    records: list[SourceFreshnessRecord] = []
    unknown_source_names: list[str] = []
    preserved_source_names: list[str] = []
    generated_source_names: list[str] = []
    load_result_by_source: dict[str, Any] = {result.source_name: result for result in load_results}
    previous_record_by_source: dict[str, SourceFreshnessRecord] = {
        record.source_name: record for record in previous_records
    }

    source: SourceEntry
    for source in sources:
        load_result: Any | None = load_result_by_source.get(source.name)
        if _is_soft_skipped_load(load_result):
            previous_record: SourceFreshnessRecord | None = previous_record_by_source.get(
                source.name
            )
            if previous_record is None:
                unknown_source_names.append(source.name)
                continue
            records.append(previous_record)
            preserved_source_names.append(source.name)
            continue

        if source.managed:
            if load_result is None or str(load_result.status) != "success":
                unknown_source_names.append(source.name)
                continue
            managed_record: SourceFreshnessRecord | None = _managed_loader_freshness_record(
                adapter=adapter,
                connection=connection,
                source=source,
                virtual_environment_name=virtual_environment_name,
                observed_at=observed_at,
                run_id=run_id,
            )
            if managed_record is None:
                unknown_source_names.append(source.name)
                continue
            records.append(
                _record_with_lag_tolerance_applied(
                    source=source,
                    current_record=managed_record,
                    previous_record=previous_record_by_source.get(source.name),
                )
            )
            if source.freshness is None:
                generated_source_names.append(source.name)
            continue

        observation: SourceFreshnessObservation | None = _observe_unmanaged_source_freshness(
            adapter=adapter,
            connection=connection,
            source=source,
            observed_at=observed_at,
        )
        if observation is None:
            unknown_source_names.append(source.name)
            continue
        current_record: SourceFreshnessRecord = source_freshness_record_from_observation(
            observation=observation,
            virtual_environment_name=virtual_environment_name,
        )
        records.append(
            _record_with_lag_tolerance_applied(
                source=source,
                current_record=current_record,
                previous_record=previous_record_by_source.get(source.name),
            )
        )

    return SourceFreshnessRuntimeResult(
        records=tuple(sorted(records, key=lambda record: record.source_name)),
        unknown_source_names=tuple(sorted(unknown_source_names)),
        preserved_source_names=tuple(sorted(preserved_source_names)),
        generated_source_names=tuple(sorted(generated_source_names)),
    )


def persist_virtual_environment_source_freshness(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    virtual_environment_name: str,
    result: SourceFreshnessRuntimeResult,
) -> None:
    """Persist the latest observed freshness records for a virtual environment."""

    backend.replace_virtual_environment_source_freshness(
        connection=state_connection,
        schema=schema,
        virtual_environment_name=virtual_environment_name,
        records=result.records,
    )


def build_current_virtual_source_freshness_records(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    virtual_environment_name: str,
    observed_at: datetime,
    previous_records: tuple[SourceFreshnessRecord, ...],
    run_id: str | None = None,
) -> tuple[SourceFreshnessRecord, ...]:
    """Return source records for pre-loader virtual freshness comparisons."""

    unmanaged_sources: tuple[SourceEntry, ...] = tuple(
        source for source in sources if not source.managed
    )
    current_unmanaged_result: SourceFreshnessRuntimeResult = (
        observe_virtual_environment_source_freshness(
            adapter=adapter,
            connection=connection,
            sources=unmanaged_sources,
            virtual_environment_name=virtual_environment_name,
            observed_at=observed_at,
        )
    )
    managed_sources: tuple[SourceEntry, ...] = tuple(source for source in sources if source.managed)
    managed_source_names: frozenset[str] = frozenset(source.name for source in managed_sources)
    sources_by_name: dict[str, SourceEntry] = {source.name: source for source in unmanaged_sources}
    previous_records_by_source: dict[str, SourceFreshnessRecord] = {
        record.source_name: record for record in previous_records
    }
    previous_managed_records: tuple[SourceFreshnessRecord, ...] = tuple(
        record for record in previous_records if record.source_name in managed_source_names
    )
    previous_managed_source_names: frozenset[str] = frozenset(
        record.source_name for record in previous_managed_records
    )
    generated_managed_records: tuple[SourceFreshnessRecord, ...] = ()
    if run_id is not None:
        generated_managed_records = tuple(
            _generated_managed_loader_record(
                source=source,
                virtual_environment_name=virtual_environment_name,
                observed_at=observed_at,
                run_id=run_id,
            )
            for source in managed_sources
            if source.freshness is None and source.name not in previous_managed_source_names
        )
    current_unmanaged_records: tuple[SourceFreshnessRecord, ...] = tuple(
        _record_with_lag_tolerance_applied(
            source=sources_by_name[record.source_name],
            current_record=record,
            previous_record=previous_records_by_source.get(record.source_name),
        )
        for record in current_unmanaged_result.records
    )
    return tuple(
        sorted(
            (*previous_managed_records, *generated_managed_records, *current_unmanaged_records),
            key=lambda record: record.source_name,
        )
    )


def _record_with_lag_tolerance_applied(
    *,
    source: SourceEntry,
    current_record: SourceFreshnessRecord,
    previous_record: SourceFreshnessRecord | None,
) -> SourceFreshnessRecord:
    if previous_record is None or source.freshness is None:
        return current_record
    if source_freshness_records_equivalent(
        previous_record=previous_record,
        current_record=current_record,
        lag_tolerance=source.freshness.lag_tolerance,
    ):
        return previous_record
    return current_record


def _generated_managed_loader_record(
    *,
    source: SourceEntry,
    virtual_environment_name: str,
    observed_at: datetime,
    run_id: str,
) -> SourceFreshnessRecord:
    return SourceFreshnessRecord(
        virtual_environment_name=virtual_environment_name,
        source_name=source.name,
        strategy="loader",
        value_kind=SourceFreshnessValueKind.STRING.value,
        data_version=run_id,
        data_version_hash=source_freshness_data_version_hash(
            source_name=source.name,
            strategy="loader",
            value_kind=SourceFreshnessValueKind.STRING,
            data_version=run_id,
        ),
        observed_at=observed_at,
    )


def _observe_unmanaged_source_freshness(
    *,
    adapter: StrictAdapter,
    connection: Any,
    source: SourceEntry,
    observed_at: datetime,
) -> SourceFreshnessObservation | None:
    try:
        if source.freshness is not None:
            return observe_configured_source_freshness(
                adapter=adapter,
                connection=connection,
                source=source,
                observed_at=observed_at,
            )
        if (
            not source.managed
            and source.expression is None
            and source.table is not None
            and adapter.supports_table_freshness_metadata()
        ):
            return observe_configured_source_freshness(
                adapter=adapter,
                connection=connection,
                source=_source_with_adapter_freshness(source),
                observed_at=observed_at,
            )
    except AdapterUserError:
        return None
    return None


def _managed_loader_freshness_record(
    *,
    adapter: StrictAdapter,
    connection: Any,
    source: SourceEntry,
    virtual_environment_name: str,
    observed_at: datetime,
    run_id: str | None,
) -> SourceFreshnessRecord | None:
    if source.freshness is not None:
        try:
            observation: SourceFreshnessObservation = observe_configured_source_freshness(
                adapter=adapter,
                connection=connection,
                source=source,
                observed_at=observed_at,
            )
        except AdapterUserError:
            return None
        return source_freshness_record_from_observation(
            observation=observation,
            virtual_environment_name=virtual_environment_name,
        )
    if run_id is None:
        return None
    return _generated_managed_loader_record(
        source=source,
        virtual_environment_name=virtual_environment_name,
        observed_at=observed_at,
        run_id=run_id,
    )


def _is_soft_skipped_load(load_result: Any | None) -> bool:
    return (
        load_result is not None
        and str(load_result.status) == "skipped"
        and str(load_result.skip_mode) == "soft"
    )


def _source_with_adapter_freshness(source: SourceEntry) -> SourceEntry:
    return SourceEntry(
        name=source.name,
        database=source.database,
        schema=source.schema,
        table=source.table,
        loader=source.loader,
        managed=source.managed,
        integration_loader=source.integration_loader,
        freshness=SourceFreshnessConfig(strategy=SourceFreshnessStrategy.ADAPTER),
        write_strategy=source.write_strategy,
        load_batch_size=source.load_batch_size,
        cursor_column=source.cursor_column,
        unique_key=source.unique_key,
        expression=source.expression,
        description=source.description,
        type_enforcement=source.type_enforcement,
        contract=source.contract,
        meta=source.meta,
        columns=source.columns,
        audits=source.audits,
    )
