"""Direct source freshness read operations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.compiler.source_freshness._helpers.sql import (
    build_qualified_table_name,
)
from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessInputError
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
    SourceFreshnessSet,
)


def read_latest_source_freshness(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    table_exists: bool,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_read_latest_sql: Callable[..., str],
    source_names: tuple[str, ...] | None = None,
) -> SourceFreshnessSet:
    """Read latest source freshness rows, trusting the caller-resolved table existence."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    if not table_exists:
        return SourceFreshnessSet(schema=schema, records={})

    read_sql: str = render_read_latest_sql(
        database=database,
        schema=schema,
    )
    if source_names is not None:
        if not source_names:
            return SourceFreshnessSet(schema=schema, records={})
        literals: str = ", ".join(
            "'" + source_name.replace("'", "''") + "'" for source_name in source_names
        )
        read_sql = (
            f"SELECT * FROM ({read_sql}) AS __sqlbuild_relevant "
            f"WHERE source_name IN ({literals})"
        )
    try:
        result: Any = execute(connection=connection, sql=read_sql)
    except Exception as error:
        raise SourceFreshnessInputError(
            f"Unable to read source freshness records from {qualified_name}. This can happen "
            "after upgrading from an older sqlbuild version; delete or rebuild the SQLBuild "
            "source freshness table to regenerate source freshness state."
        ) from error
    rows: list[tuple[Any, ...]] = result.fetchall()
    records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {}
    row: tuple[Any, ...]
    for row in rows:
        record: SourceFreshnessRecord = _row_to_source_freshness_record(row)
        records[record.identity] = record
    return SourceFreshnessSet(schema=schema, records=records)


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
