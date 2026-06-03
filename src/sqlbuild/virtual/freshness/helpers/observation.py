"""Helpers for observing configured source freshness."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.shared.models import QueryResult, TableFreshnessMetadata
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from sqlbuild.virtual.freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.virtual.freshness.models import SourceFreshnessObservation


def observe_configured_source_freshness(
    *,
    adapter: StrictAdapter,
    connection: Any,
    source: SourceEntry,
    observed_at: datetime,
) -> SourceFreshnessObservation:
    """Observe one source freshness config and return a comparable data version."""

    config: SourceFreshnessConfig | None = source.freshness
    if config is None:
        raise SourceFreshnessObservationError(
            f"source '{source.name}' does not define freshness configuration"
        )
    if config.strategy == SourceFreshnessStrategy.ADAPTER:
        return _observe_adapter_freshness(
            adapter=adapter,
            connection=connection,
            source=source,
            observed_at=observed_at,
        )

    if config.strategy == SourceFreshnessStrategy.COLUMN:
        if config.column is None or config.value_kind is None:
            raise SourceFreshnessObservationError(
                f"source '{source.name}' has incomplete column freshness configuration"
            )
        sql: str = (
            f"SELECT MAX({adapter.render_identifier(config.column)}) AS data_version "
            f"FROM {_source_relation(source)}"
        )
        data_version: object = _query_single_data_version(
            adapter=adapter,
            connection=connection,
            source_name=source.name,
            sql=sql,
        )
        return SourceFreshnessObservation(
            source_name=source.name,
            strategy=config.strategy,
            data_version=data_version,
            value_kind=config.value_kind,
            observed_at=observed_at,
        )

    if config.query is None or config.value_kind is None:
        raise SourceFreshnessObservationError(
            f"source '{source.name}' has incomplete sql freshness configuration"
        )
    data_version = _query_single_data_version(
        adapter=adapter,
        connection=connection,
        source_name=source.name,
        sql=config.query,
    )
    return SourceFreshnessObservation(
        source_name=source.name,
        strategy=config.strategy,
        data_version=data_version,
        value_kind=config.value_kind,
        observed_at=observed_at,
    )


def _observe_adapter_freshness(
    *,
    adapter: StrictAdapter,
    connection: Any,
    source: SourceEntry,
    observed_at: datetime,
) -> SourceFreshnessObservation:
    if not adapter.supports_table_freshness_metadata():
        raise SourceFreshnessObservationError(
            f"adapter '{adapter.adapter_name}' does not support table freshness metadata"
        )
    if source.expression is not None or source.table is None:
        raise SourceFreshnessObservationError(
            f"source '{source.name}' adapter freshness requires a physical table source"
        )
    metadata: TableFreshnessMetadata = adapter.get_table_freshness_metadata(
        connection,
        database=source.database,
        schema=source.schema,
        name=source.table,
    )
    if metadata.data_version is None:
        raise SourceFreshnessObservationError(
            f"source '{source.name}' freshness data_version cannot be null"
        )
    return SourceFreshnessObservation(
        source_name=source.name,
        strategy=SourceFreshnessStrategy.ADAPTER,
        data_version=metadata.data_version,
        value_kind=SourceFreshnessValueKind(metadata.value_kind),
        observed_at=metadata.observed_at or observed_at,
    )


def _query_single_data_version(
    *,
    adapter: StrictAdapter,
    connection: Any,
    source_name: str,
    sql: str,
) -> object:
    result: QueryResult = adapter.query(connection, sql, limit=None)
    if len(result.columns) != 1:
        raise SourceFreshnessObservationError(
            f"source '{source_name}' freshness query must return exactly one column"
        )
    if len(result.rows) != 1:
        raise SourceFreshnessObservationError(
            f"source '{source_name}' freshness query must return exactly one row"
        )
    data_version: object = result.rows[0][0]
    if data_version is None:
        raise SourceFreshnessObservationError(
            f"source '{source_name}' freshness data_version cannot be null"
        )
    return data_version


def _source_relation(source: SourceEntry) -> str:
    if source.expression is not None or source.table is None:
        raise SourceFreshnessObservationError(
            f"source '{source.name}' column freshness requires a physical table source"
        )
    parts: tuple[str, ...] = tuple(
        part for part in (source.database, source.schema, source.table) if part is not None
    )
    return ".".join(parts)
