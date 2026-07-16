"""Source freshness command observation helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.cli.commands.models import (
    FreshnessCommandResult,
    FreshnessSourceResult,
)
from sqlbuild.cli.commands.types import FreshnessSourceStatus
from sqlbuild.compiler.source_freshness.main.adapter_observation import (
    observe_adapter_sources_freshness,
)
from sqlbuild.compiler.source_freshness.main.age_policy import (
    evaluate_source_freshness_age_policy,
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
from sqlbuild.compiler.source_freshness.main.record_equivalence import (
    source_freshness_records_equivalent,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessObservation,
    SourceFreshnessRecord,
)
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from sqlbuild.spec.contracts.models import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.contracts.types import SourceFreshnessStrategy


def observe_source_freshness_for_command(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    observed_at: datetime,
    previous_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] | None = None,
    previous_records_by_source_name: dict[str, SourceFreshnessRecord] | None = None,
) -> FreshnessCommandResult:
    """Observe current source freshness for the CLI command."""

    selected_sources: tuple[SourceEntry, ...] = _selected_sources(
        sources=sources,
        select=select,
        exclude=exclude,
    )
    results: list[FreshnessSourceResult] = []
    previous_by_identity: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = (
        previous_records if previous_records is not None else {}
    )
    previous_by_source_name: dict[str, SourceFreshnessRecord] = (
        previous_records_by_source_name if previous_records_by_source_name is not None else {}
    )
    compare_state: bool = (
        previous_records is not None or previous_records_by_source_name is not None
    )
    observation_sources_by_name: dict[str, SourceEntry] = {}
    adapter_observation_sources: list[SourceEntry] = []
    source: SourceEntry
    for source in selected_sources:
        observation_source: SourceEntry | None = _source_for_observation(
            adapter=adapter,
            source=source,
        )
        if observation_source is None:
            results.append(
                FreshnessSourceResult(
                    name=source.name,
                    status=FreshnessSourceStatus.UNKNOWN,
                    target_database=source.database,
                    target_schema=source.schema,
                    target_name=source.table,
                    message="no freshness config and adapter metadata unavailable",
                )
            )
            continue
        observation_sources_by_name[source.name] = observation_source
        if observation_source.freshness is not None and (
            observation_source.freshness.strategy == SourceFreshnessStrategy.ADAPTER
        ):
            adapter_observation_sources.append(observation_source)

    adapter_observations: dict[str, SourceFreshnessObservation] = {}
    adapter_observation_error: Exception | None = None
    if adapter_observation_sources:
        try:
            adapter_observations = observe_adapter_sources_freshness(
                adapter=adapter,
                connection=connection,
                sources=tuple(adapter_observation_sources),
                observed_at=observed_at,
            )
        except Exception as exc:
            adapter_observation_error = exc

    for source_name, observation_source in observation_sources_by_name.items():
        if observation_source.freshness is not None and (
            observation_source.freshness.strategy == SourceFreshnessStrategy.ADAPTER
        ):
            if adapter_observation_error is not None:
                results.append(
                    FreshnessSourceResult(
                        name=source_name,
                        status=FreshnessSourceStatus.ERROR,
                        target_database=observation_source.database,
                        target_schema=observation_source.schema,
                        target_name=observation_source.table,
                        message=str(adapter_observation_error),
                    )
                )
                continue
            observation: SourceFreshnessObservation | None = adapter_observations.get(source_name)
            if observation is None:
                results.append(
                    FreshnessSourceResult(
                        name=source_name,
                        status=FreshnessSourceStatus.ERROR,
                        target_database=observation_source.database,
                        target_schema=observation_source.schema,
                        target_name=observation_source.table,
                        message="freshness metadata was not returned",
                    )
                )
                continue
        else:
            try:
                observation = observe_configured_source_freshness(
                    adapter=adapter,
                    connection=connection,
                    source=observation_source,
                    observed_at=observed_at,
                )
            except Exception as exc:
                results.append(
                    FreshnessSourceResult(
                        name=source_name,
                        status=FreshnessSourceStatus.ERROR,
                        target_database=observation_source.database,
                        target_schema=observation_source.schema,
                        target_name=observation_source.table,
                        message=str(exc),
                    )
                )
                continue
        record: SourceFreshnessRecord = _record_from_observation(
            observation=observation,
            source=observation_source,
            run_id="freshness",
        )
        results.append(
            _source_result_from_record(
                name=source_name,
                current_record=record,
                previous_record=previous_by_identity.get(record.identity)
                or previous_by_source_name.get(record.source_name),
                lag_tolerance=observation_source.freshness.lag_tolerance
                if observation_source.freshness is not None
                else None,
                age_status=evaluate_source_freshness_age_policy(
                    policy=observation_source.freshness.age_policy
                    if observation_source.freshness is not None
                    else None,
                    data_version=observation.data_version,
                    observed_at=observation.observed_at,
                ),
                compare_state=compare_state,
            )
        )
    return FreshnessCommandResult(sources=tuple(sorted(results, key=lambda item: item.name)))


def _record_from_observation(
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


def _source_result_from_record(
    *,
    name: str,
    current_record: SourceFreshnessRecord,
    previous_record: SourceFreshnessRecord | None,
    lag_tolerance: str | None,
    age_status: SourceFreshnessAgeStatus | None,
    compare_state: bool,
) -> FreshnessSourceResult:
    if previous_record is None:
        if compare_state:
            return FreshnessSourceResult(
                name=name,
                status=FreshnessSourceStatus.UNKNOWN,
                strategy=current_record.strategy,
                value_kind=current_record.value_kind,
                current_data_version=current_record.data_version,
                lag_tolerance=lag_tolerance,
                target_database=current_record.target_database,
                target_schema=current_record.target_schema,
                target_name=current_record.target_name,
                message="previous source freshness state missing",
                age_status=age_status,
            )
        return FreshnessSourceResult(
            name=name,
            status=FreshnessSourceStatus.OBSERVED,
            strategy=current_record.strategy,
            value_kind=current_record.value_kind,
            current_data_version=current_record.data_version,
            lag_tolerance=lag_tolerance,
            target_database=current_record.target_database,
            target_schema=current_record.target_schema,
            target_name=current_record.target_name,
            age_status=age_status,
        )
    equivalent: bool = source_freshness_records_equivalent(
        previous_record=previous_record,
        current_record=current_record,
        lag_tolerance=lag_tolerance,
    )
    status: FreshnessSourceStatus
    if equivalent and previous_record.data_version_hash == current_record.data_version_hash:
        status = FreshnessSourceStatus.UNCHANGED
    elif equivalent:
        status = FreshnessSourceStatus.TOLERATED
    else:
        status = FreshnessSourceStatus.CHANGED
    return FreshnessSourceResult(
        name=name,
        status=status,
        strategy=current_record.strategy,
        value_kind=current_record.value_kind,
        current_data_version=current_record.data_version,
        previous_data_version=previous_record.data_version,
        lag_tolerance=lag_tolerance,
        target_database=current_record.target_database,
        target_schema=current_record.target_schema,
        target_name=current_record.target_name,
        age_status=age_status,
    )


def _selected_sources(
    *, sources: tuple[SourceEntry, ...], select: tuple[str, ...], exclude: tuple[str, ...]
) -> tuple[SourceEntry, ...]:
    selected_names: frozenset[str] = frozenset(select)
    excluded_names: frozenset[str] = frozenset(exclude)
    return tuple(
        source
        for source in sources
        if (not selected_names or source.name in selected_names)
        and source.name not in excluded_names
    )


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
