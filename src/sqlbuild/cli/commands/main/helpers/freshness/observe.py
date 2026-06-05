"""Source freshness command observation helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.cli.commands.main.helpers.freshness.models import (
    FreshnessCommandResult,
    FreshnessSourceResult,
)
from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.normalization import (
    normalize_source_freshness_data_version,
)
from sqlbuild.compiler.source_freshness.main.observation import observe_configured_source_freshness
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessObservation,
    SourceFreshnessRecord,
)
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy


def observe_source_freshness_for_command(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    observed_at: datetime,
) -> FreshnessCommandResult:
    """Observe current source freshness for the CLI command."""

    selected_sources: tuple[SourceEntry, ...] = _selected_sources(
        sources=sources,
        select=select,
        exclude=exclude,
    )
    results: list[FreshnessSourceResult] = []
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
                    status="unknown",
                    target_database=source.database,
                    target_schema=source.schema,
                    target_name=source.table,
                    message="no freshness config and adapter metadata unavailable",
                )
            )
            continue
        try:
            observation: SourceFreshnessObservation = observe_configured_source_freshness(
                adapter=adapter,
                connection=connection,
                source=observation_source,
                observed_at=observed_at,
            )
        except Exception as exc:
            results.append(
                FreshnessSourceResult(
                    name=source.name,
                    status="error",
                    target_database=source.database,
                    target_schema=source.schema,
                    target_name=source.table,
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
            FreshnessSourceResult(
                name=source.name,
                status="observed",
                strategy=record.strategy,
                value_kind=record.value_kind,
                current_data_version=record.data_version,
                lag_tolerance=observation_source.freshness.lag_tolerance
                if observation_source.freshness is not None
                else None,
                target_database=source.database,
                target_schema=source.schema,
                target_name=source.table,
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
