"""Standard source freshness planning observation and comparison helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.normalization import (
    normalize_source_freshness_data_version,
)
from sqlbuild.compiler.source_freshness.main.observation import observe_configured_source_freshness
from sqlbuild.compiler.source_freshness.main.read import read_latest_source_freshness
from sqlbuild.compiler.source_freshness.main.record_equivalence import (
    source_freshness_records_equivalent,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessObservation,
    SourceFreshnessRecord,
    SourceFreshnessSet,
    StandardSourceFreshnessPlanningResult,
)
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy


def build_standard_source_freshness_planning_result(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    state_database: str | None,
    state_schemas: tuple[str, ...],
    observed_at: datetime,
    run_id: str,
    render_qualified_name: Callable[..., str | None],
) -> StandardSourceFreshnessPlanningResult:
    previous_records_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = (
        _read_previous_records(
            adapter=adapter,
            connection=connection,
            state_database=state_database,
            state_schemas=state_schemas,
            render_qualified_name=render_qualified_name,
        )
    )
    observed_records: list[SourceFreshnessRecord] = []
    unknown_source_names: list[str] = []
    changed_identities: set[SourceFreshnessIdentity] = set()
    unchanged_identities: set[SourceFreshnessIdentity] = set()

    source: SourceEntry
    for source in sources:
        if source.managed:
            continue
        observation_source: SourceEntry | None = _source_for_observation(
            adapter=adapter,
            source=source,
        )
        if observation_source is None:
            unknown_source_names.append(source.name)
            continue

        try:
            observation: SourceFreshnessObservation = observe_configured_source_freshness(
                adapter=adapter,
                connection=connection,
                source=observation_source,
                observed_at=observed_at,
            )
        except AdapterUserError:
            unknown_source_names.append(source.name)
            continue
        observed_record: SourceFreshnessRecord = source_freshness_record_from_observation(
            observation=observation,
            source=observation_source,
            run_id=run_id,
        )
        observed_records.append(observed_record)
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

    return StandardSourceFreshnessPlanningResult(
        observed_records=tuple(sorted(observed_records, key=lambda record: str(record.identity))),
        previous_records=tuple(
            sorted(previous_records_by_identity.values(), key=lambda record: str(record.identity))
        ),
        changed_identities=frozenset(changed_identities),
        unchanged_identities=frozenset(unchanged_identities),
        unknown_source_names=tuple(sorted(unknown_source_names)),
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
) -> dict[SourceFreshnessIdentity, SourceFreshnessRecord]:
    previous_records_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {}
    state_schema: str
    for state_schema in state_schemas:
        previous_set: SourceFreshnessSet = read_latest_source_freshness(
            connection=connection,
            execute=adapter.execute,
            relation_exists=adapter.relation_exists,
            database=state_database,
            schema=state_schema,
            render_qualified_name=render_qualified_name,
        )
        _merge_latest_previous_records(
            previous_records_by_identity=previous_records_by_identity,
            candidate_records=previous_set.records,
        )
    return previous_records_by_identity


def _merge_latest_previous_records(
    *,
    previous_records_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord],
    candidate_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord],
) -> None:
    identity: SourceFreshnessIdentity
    candidate_record: SourceFreshnessRecord
    for identity, candidate_record in candidate_records.items():
        previous_record: SourceFreshnessRecord | None = previous_records_by_identity.get(identity)
        if previous_record is None or candidate_record.observed_at > previous_record.observed_at:
            previous_records_by_identity[identity] = candidate_record


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
