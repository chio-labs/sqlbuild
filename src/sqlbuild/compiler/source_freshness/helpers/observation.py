"""Shared source freshness observation helper implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.models import (
    QueryResult,
    TableFreshnessMetadata,
    TableFreshnessRequest,
)
from sqlbuild.compiler.helpers.sources import render_source_relation
from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.compiler.source_freshness.models import SourceFreshnessObservation
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind


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
        where_sql: str = f" WHERE {config.filter}" if config.filter is not None else ""
        sql: str = adapter.render_source_freshness_max_query(
            column=config.column,
            source_relation=render_source_relation(entry=source, adapter=adapter),
            source_is_subquery=source.expression is not None,
            where_sql=where_sql,
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
        connection=connection,
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


def observe_adapter_sources_freshness(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    observed_at: datetime,
) -> dict[str, SourceFreshnessObservation]:
    """Observe adapter metadata freshness for physical table sources in one batch."""

    if not sources:
        return {}
    if not adapter.supports_table_freshness_metadata():
        raise SourceFreshnessObservationError(
            f"adapter '{adapter.adapter_name}' does not support table freshness metadata"
        )
    requests_by_source_name: dict[str, TableFreshnessRequest] = {}
    source: SourceEntry
    for source in sources:
        if source.expression is not None or source.table is None:
            raise SourceFreshnessObservationError(
                f"source '{source.name}' adapter freshness requires a physical table source"
            )
        requests_by_source_name[source.name] = TableFreshnessRequest(
            database=source.database,
            schema=source.schema,
            name=source.table,
        )

    metadata_by_request: dict[TableFreshnessRequest, TableFreshnessMetadata] = (
        adapter.get_tables_freshness_metadata(
            connection=connection,
            requests=tuple(requests_by_source_name.values()),
        )
    )
    observations: dict[str, SourceFreshnessObservation] = {}
    for source in sources:
        request: TableFreshnessRequest = requests_by_source_name[source.name]
        metadata: TableFreshnessMetadata | None = metadata_by_request.get(request)
        if metadata is None:
            raise SourceFreshnessObservationError(
                f"source '{source.name}' freshness metadata was not returned"
            )
        if metadata.data_version is None:
            raise SourceFreshnessObservationError(
                f"source '{source.name}' freshness data_version cannot be null"
            )
        observations[source.name] = SourceFreshnessObservation(
            source_name=source.name,
            strategy=SourceFreshnessStrategy.ADAPTER,
            data_version=metadata.data_version,
            value_kind=SourceFreshnessValueKind(metadata.value_kind),
            observed_at=metadata.observed_at or observed_at,
        )
    return observations


def _query_single_data_version(
    *,
    adapter: StrictAdapter,
    connection: Any,
    source_name: str,
    sql: str,
) -> object:
    try:
        result: QueryResult = adapter.query(connection=connection, sql=sql, limit=None)
    except Exception as exc:
        raise SourceFreshnessObservationError(
            f"source '{source_name}' freshness query failed: {exc}"
        ) from exc
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
