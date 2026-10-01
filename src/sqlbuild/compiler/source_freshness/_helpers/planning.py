"""Direct source freshness planning observation and comparison helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.compiler.source_freshness._helpers.age_policy import (
    evaluate_source_freshness_age_policy,
)
from sqlbuild.compiler.source_freshness.constants import (
    INCOMPLETE_CONFIGURATION_ERROR_FRAGMENT,
    PHYSICAL_TABLE_SOURCE_ERROR_FRAGMENT,
)
from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.compiler.source_freshness.main.adapter_observation import (
    observe_adapter_sources_freshness,
)
from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.normalization import (
    normalize_source_freshness_data_version,
)
from sqlbuild.compiler.source_freshness.main.observation import (
    observe_configured_source_freshness,
)
from sqlbuild.compiler.source_freshness.main.read import read_latest_source_freshness
from sqlbuild.compiler.source_freshness.main.record_equivalence import (
    source_freshness_records_equivalent,
)
from sqlbuild.compiler.source_freshness.models import (
    AdapterSourceFreshnessBatch,
    DirectSourceFreshnessPlanningResult,
    SourceFreshnessIdentity,
    SourceFreshnessObservation,
    SourceFreshnessRecord,
    SourceFreshnessSet,
    SourceFreshnessUnknown,
)
from sqlbuild.compiler.source_freshness.types import (
    SourceFreshnessAgeStatus,
    SourceFreshnessUnknownReason,
)
from sqlbuild.spec.contracts.models import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.contracts.types import SourceFreshnessStrategy


def build_direct_source_freshness_planning_result(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    state_database: str | None,
    state_schemas: tuple[str, ...],
    observed_at: datetime,
    run_id: str,
    render_qualified_name: Callable[..., str | None],
    state_table_exists_by_schema: dict[str, bool],
    filter_previous_to_sources: bool = False,
) -> DirectSourceFreshnessPlanningResult:
    previous_records_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = (
        _read_previous_records(
            adapter=adapter,
            connection=connection,
            state_database=state_database,
            state_schemas=state_schemas,
            render_qualified_name=render_qualified_name,
            state_table_exists_by_schema=state_table_exists_by_schema,
            source_names=(
                tuple(sorted(source.name for source in sources))
                if filter_previous_to_sources
                else None
            ),
        )
    )
    observed_records: list[SourceFreshnessRecord] = []
    unconfigured_sources: dict[str, SourceFreshnessUnknown] = {}
    changed_identities: set[SourceFreshnessIdentity] = set()
    unchanged_identities: set[SourceFreshnessIdentity] = set()
    age_statuses: dict[SourceFreshnessIdentity, SourceFreshnessAgeStatus] = {}
    observation_sources_by_name: dict[str, SourceEntry] = {}
    adapter_observation_sources: list[SourceEntry] = []

    source: SourceEntry
    for source in sources:
        if source.managed:
            continue
        observation_source: SourceEntry | None = _source_for_observation(
            adapter=adapter,
            source=source,
        )
        if observation_source is None:
            unconfigured_sources[source.name] = SourceFreshnessUnknown(
                source_name=source.name,
                reason=SourceFreshnessUnknownReason.NO_FRESHNESS_CONFIG,
                message="no freshness config and adapter metadata unavailable",
            )
            continue
        observation_sources_by_name[source.name] = observation_source
        if observation_source.freshness is not None and (
            observation_source.freshness.strategy == SourceFreshnessStrategy.ADAPTER
        ):
            adapter_observation_sources.append(observation_source)

    adapter_batch: AdapterSourceFreshnessBatch = _observe_adapter_batch(
        adapter=adapter,
        connection=connection,
        sources=tuple(adapter_observation_sources),
        observed_at=observed_at,
    )
    unknown_sources: dict[str, SourceFreshnessUnknown] = {
        **unconfigured_sources,
        **adapter_batch.unknown,
    }

    for source_name, observation_source in observation_sources_by_name.items():
        if observation_source.freshness is not None and (
            observation_source.freshness.strategy == SourceFreshnessStrategy.ADAPTER
        ):
            observation: SourceFreshnessObservation | None = adapter_batch.observations.get(
                source_name
            )
            if observation is None:
                continue
        else:
            try:
                observation = observe_configured_source_freshness(
                    adapter=adapter,
                    connection=connection,
                    source=observation_source,
                    observed_at=observed_at,
                )
            except AdapterUserError as exc:
                unknown_sources[source_name] = _error_unknown(
                    source_name=source_name, message=exc.message
                )
                continue
            except SourceFreshnessObservationError as exc:
                if _source_freshness_error_is_configuration_error(error=exc):
                    raise
                unknown_sources[source_name] = _error_unknown(
                    source_name=source_name, message=str(exc)
                )
                continue
        observed_record: SourceFreshnessRecord = source_freshness_record_from_observation(
            observation=observation,
            source=observation_source,
            run_id=run_id,
        )
        observed_records.append(observed_record)
        age_status: SourceFreshnessAgeStatus | None = evaluate_source_freshness_age_policy(
            policy=observation_source.freshness.age_policy
            if observation_source.freshness is not None
            else None,
            data_version=observation.data_version,
            observed_at=observation.observed_at,
        )
        if age_status is not None:
            age_statuses[observed_record.identity] = age_status
        previous_record: SourceFreshnessRecord | None = previous_records_by_identity.get(
            observed_record.identity
        )
        if previous_record is None:
            changed_identities.add(observed_record.identity)
            continue
        if source_freshness_records_equivalent(
            previous_record=previous_record,
            current_record=observed_record,
            lag_tolerance=observation_source.freshness.lag_tolerance
            if observation_source.freshness is not None
            else None,
        ):
            unchanged_identities.add(observed_record.identity)
        else:
            changed_identities.add(observed_record.identity)

    return DirectSourceFreshnessPlanningResult(
        observed_records=tuple(sorted(observed_records, key=lambda record: str(record.identity))),
        previous_records=tuple(
            sorted(previous_records_by_identity.values(), key=lambda record: str(record.identity))
        ),
        changed_identities=frozenset(changed_identities),
        unchanged_identities=frozenset(unchanged_identities),
        unknown_source_names=tuple(sorted(unknown_sources)),
        unknown_sources=dict(sorted(unknown_sources.items())),
        age_statuses=age_statuses,
    )


def _observe_adapter_batch(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    observed_at: datetime,
) -> AdapterSourceFreshnessBatch:
    try:
        return observe_adapter_sources_freshness(
            adapter=adapter,
            connection=connection,
            sources=sources,
            observed_at=observed_at,
        )
    except (AdapterUserError, SourceFreshnessObservationError) as exc:
        message: str = exc.message if isinstance(exc, AdapterUserError) else str(exc)
        return AdapterSourceFreshnessBatch(
            unknown={
                source.name: _error_unknown(source_name=source.name, message=message)
                for source in sources
            }
        )


def _error_unknown(*, source_name: str, message: str) -> SourceFreshnessUnknown:
    return SourceFreshnessUnknown(
        source_name=source_name,
        reason=SourceFreshnessUnknownReason.ERROR,
        message=message,
    )


def _source_freshness_error_is_configuration_error(
    *, error: SourceFreshnessObservationError
) -> bool:
    message: str = str(error)
    return (
        PHYSICAL_TABLE_SOURCE_ERROR_FRAGMENT in message
        or INCOMPLETE_CONFIGURATION_ERROR_FRAGMENT in message
    )


def source_freshness_record_from_observation(
    *, observation: SourceFreshnessObservation, source: SourceEntry, run_id: str
) -> SourceFreshnessRecord:
    normalized_data_version: str = normalize_source_freshness_data_version(
        value=observation.data_version,
        value_kind=observation.value_kind,
    )
    return SourceFreshnessRecord(
        source_name=observation.source_name,
        target_database=source.database,
        target_schema=source.schema,
        target_name=source.table,
        run_id=run_id,
        strategy=observation.strategy.value,
        value_kind=observation.value_kind.value,
        data_version=normalized_data_version,
        data_version_hash=source_freshness_data_version_hash(
            source_name=observation.source_name,
            strategy=observation.strategy,
            value_kind=observation.value_kind,
            data_version=normalized_data_version,
        ),
        observed_at=observation.observed_at,
    )


def _read_previous_records(
    *,
    adapter: StrictAdapter,
    connection: Any,
    state_database: str | None,
    state_schemas: tuple[str, ...],
    render_qualified_name: Callable[..., str | None],
    state_table_exists_by_schema: dict[str, bool],
    source_names: tuple[str, ...] | None,
) -> dict[SourceFreshnessIdentity, SourceFreshnessRecord]:
    previous_records_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {}
    state_schema: str
    for state_schema in state_schemas:
        table_exists: bool = state_table_exists_by_schema.get(state_schema, False)
        previous_set: SourceFreshnessSet = read_latest_source_freshness(
            connection=connection,
            execute=adapter.execute,
            table_exists=table_exists,
            database=state_database,
            schema=state_schema,
            render_qualified_name=render_qualified_name,
            render_read_latest_sql=adapter.render_read_latest_source_freshness_sql,
            source_names=source_names,
        )
        previous_records_by_identity = _merged_latest_previous_records(
            previous_records_by_identity=previous_records_by_identity,
            candidate_records=previous_set.records,
        )
    return previous_records_by_identity


def _merged_latest_previous_records(
    *,
    previous_records_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord],
    candidate_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord],
) -> dict[SourceFreshnessIdentity, SourceFreshnessRecord]:
    merged: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = dict(
        previous_records_by_identity
    )
    identity: SourceFreshnessIdentity
    candidate_record: SourceFreshnessRecord
    for identity, candidate_record in candidate_records.items():
        previous_record: SourceFreshnessRecord | None = merged.get(identity)
        if previous_record is None or candidate_record.observed_at > previous_record.observed_at:
            merged[identity] = candidate_record
    return merged


def _source_for_observation(*, adapter: StrictAdapter, source: SourceEntry) -> SourceEntry | None:
    if source.freshness is not None:
        return source
    if (
        source.expression is None
        and source.table is not None
        and adapter.supports_table_freshness_metadata()
    ):
        return _source_with_adapter_freshness(source)
    return None


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
