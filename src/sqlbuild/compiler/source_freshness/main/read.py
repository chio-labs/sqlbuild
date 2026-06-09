"""Standard source freshness read operations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessInputError
from sqlbuild.compiler.source_freshness.main.shared.helpers.sql import (
    build_qualified_table_name,
    build_read_all_sql,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
    SourceFreshnessSet,
)


def read_latest_source_freshness(
    *,
    connection: Any,
    execute: Any,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> SourceFreshnessSet:
    """Read all source freshness rows and resolve latest per source/target identity."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    if not _table_exists(connection=connection, execute=execute, qualified_name=qualified_name):
        return SourceFreshnessSet(schema=schema, records={})

    read_sql: str = build_read_all_sql(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    try:
        result: Any = execute(connection, read_sql)
    except Exception as error:
        raise SourceFreshnessInputError(
            f"Unable to read source freshness records from {qualified_name}. This can happen "
            "after upgrading from an older sqlbuild version; delete or rebuild the SQLBuild "
            "source freshness table to regenerate source freshness state."
        ) from error
    rows: list[tuple[Any, ...]] = result.fetchall()
    latest: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {}
    row: tuple[Any, ...]
    for row in rows:
        record: SourceFreshnessRecord = _row_to_source_freshness_record(row)
        identity: SourceFreshnessIdentity = record.identity
        if identity not in latest or record.observed_at > latest[identity].observed_at:
            latest[identity] = record
    return SourceFreshnessSet(schema=schema, records=latest)


def _table_exists(*, connection: Any, execute: Any, qualified_name: str) -> bool:
    """Check whether the source freshness table exists without raising on missing."""

    try:
        execute(connection, f"SELECT COUNT(*) FROM {qualified_name} WHERE 1 = 0")
        return True
    except Exception:
        return False


def _row_to_source_freshness_record(row: tuple[Any, ...]) -> SourceFreshnessRecord:
    raw_target_database: Any = row[1]
    raw_target_schema: Any = row[2]
    raw_target_name: Any = row[3]
    raw_data_version: Any = row[7]
    raw_observed_at: Any = row[9]
    observed_at: datetime = (
        raw_observed_at
        if isinstance(raw_observed_at, datetime)
        else datetime.fromisoformat(str(raw_observed_at))
    )
    return SourceFreshnessRecord(
        source_name=str(row[0]),
        target_database=str(raw_target_database) if raw_target_database is not None else None,
        target_schema=str(raw_target_schema) if raw_target_schema is not None else None,
        target_name=str(raw_target_name) if raw_target_name is not None else None,
        run_id=str(row[4]),
        strategy=str(row[5]),
        value_kind=str(row[6]),
        data_version=str(raw_data_version) if raw_data_version is not None else None,
        data_version_hash=str(row[8]),
        observed_at=observed_at,
    )
