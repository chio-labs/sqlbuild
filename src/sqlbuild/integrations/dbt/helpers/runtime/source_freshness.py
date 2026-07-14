"""dbt manifest source freshness translation helpers."""

from __future__ import annotations

import re
from typing import cast

from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError
from sqlbuild.integrations.dbt.helpers.runtime.constants import (
    DBT_SOURCE_FRESHNESS_DAY_PERIODS,
    DBT_SOURCE_FRESHNESS_HOUR_PERIODS,
    DBT_SOURCE_FRESHNESS_MINUTE_PERIODS,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestSource
from sqlbuild.spec.contracts.models import (
    SourceEntry,
    SourceFreshnessAgePolicy,
    SourceFreshnessConfig,
)
from sqlbuild.spec.contracts.types import SourceFreshnessStrategy, SourceFreshnessValueKind

_PLAIN_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def translate_manifest_sources_to_sqlbuild_sources(
    *, manifest: DbtManifestIndex
) -> tuple[SourceEntry, ...]:
    """Translate dbt manifest source nodes to SQLBuild source entries."""

    return tuple(
        _translate_source(source)
        for source in sorted(
            manifest.sources_by_unique_id.values(), key=lambda item: item.unique_id
        )
    )


def _translate_source(source: DbtManifestSource) -> SourceEntry:
    return SourceEntry(
        name=source.unique_id,
        database=source.database,
        schema=source.schema,
        table=source.identifier or source.name,
        freshness=_translate_freshness(source),
        meta={
            "dbt_unique_id": source.unique_id,
            "dbt_package_name": source.package_name,
            "dbt_source_name": source.source_name,
            "dbt_table_name": source.name,
        },
    )


def _translate_freshness(source: DbtManifestSource) -> SourceFreshnessConfig | None:
    if source.freshness is None:
        return None
    age_policy: SourceFreshnessAgePolicy | None = _translate_age_policy(
        freshness=source.freshness,
        unique_id=source.unique_id,
    )
    if source.loaded_at_query is not None:
        return SourceFreshnessConfig(
            strategy=SourceFreshnessStrategy.SQL,
            value_kind=SourceFreshnessValueKind.TIMESTAMP,
            query=source.loaded_at_query,
            age_policy=age_policy,
        )
    if source.loaded_at_field is not None:
        if _is_plain_identifier(source.loaded_at_field):
            return SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.COLUMN,
                value_kind=SourceFreshnessValueKind.TIMESTAMP,
                column=source.loaded_at_field,
                filter=source.freshness_filter,
                age_policy=age_policy,
            )
        return SourceFreshnessConfig(
            strategy=SourceFreshnessStrategy.SQL,
            value_kind=SourceFreshnessValueKind.TIMESTAMP,
            query=_loaded_at_expression_query(source),
            age_policy=age_policy,
        )
    if age_policy is None:
        return None
    return SourceFreshnessConfig(
        strategy=SourceFreshnessStrategy.ADAPTER,
        value_kind=SourceFreshnessValueKind.TIMESTAMP,
        age_policy=age_policy,
    )


def _translate_age_policy(
    *, freshness: dict[str, object], unique_id: str
) -> SourceFreshnessAgePolicy | None:
    warn_after: str | None = _translate_duration(
        value=freshness.get("warn_after"),
        unique_id=unique_id,
        field_name="warn_after",
    )
    error_after: str | None = _translate_duration(
        value=freshness.get("error_after"),
        unique_id=unique_id,
        field_name="error_after",
    )
    if warn_after is None and error_after is None:
        return None
    return SourceFreshnessAgePolicy(warn_after=warn_after, error_after=error_after)


def _translate_duration(*, value: object, unique_id: str, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise DbtInteropConfigError(
            f"dbt source '{unique_id}' freshness.{field_name} must be an object"
        )
    duration: dict[str, object] = cast(dict[str, object], value)
    count: object | None = duration.get("count")
    period: object | None = duration.get("period")
    if count is None and period is None:
        return None
    if not isinstance(count, int) or count <= 0 or not isinstance(period, str):
        raise DbtInteropConfigError(
            f"dbt source '{unique_id}' freshness.{field_name} must include positive count "
            "and period"
        )
    unit: str | None = _duration_unit(period)
    if unit is None:
        raise DbtInteropConfigError(
            f"dbt source '{unique_id}' freshness.{field_name} has unsupported period '{period}'"
        )
    return f"{count}{unit}"


def _duration_unit(period: str) -> str | None:
    normalized: str = period.strip().lower()
    if normalized in DBT_SOURCE_FRESHNESS_MINUTE_PERIODS:
        return "m"
    if normalized in DBT_SOURCE_FRESHNESS_HOUR_PERIODS:
        return "h"
    if normalized in DBT_SOURCE_FRESHNESS_DAY_PERIODS:
        return "d"
    return None


def _is_plain_identifier(value: str) -> bool:
    return _PLAIN_IDENTIFIER_PATTERN.fullmatch(value.strip()) is not None


def _loaded_at_expression_query(source: DbtManifestSource) -> str:
    query: str = f"SELECT MAX({source.loaded_at_field}) AS data_version FROM {source.relation_name}"
    if source.freshness_filter is not None:
        query += f" WHERE {source.freshness_filter}"
    return query
