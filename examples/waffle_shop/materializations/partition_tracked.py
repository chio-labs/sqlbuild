"""Partition-tracked custom materialization for the waffle shop example.

Tracks which date partitions have been materialized in a state table.
On first run, builds all partitions. On subsequent runs, identifies and
rebuilds only stale/missing partitions.
"""

from __future__ import annotations

from typing import Any

from sqlbuild.executor.custom.models import MaterializationContext, MaterializationResult


def materialize(ctx: MaterializationContext) -> MaterializationResult:
    tracking_table: str = str(ctx.config["tracking_table"])
    partition_col: str = str(ctx.config["partition_column"])
    date_start: str = str(ctx.config["date_range_start"])
    date_end: str = str(ctx.config["date_range_end"])

    ctx.adapter.execute(
        ctx.connection,
        f"CREATE TABLE IF NOT EXISTS {tracking_table} "
        f"(partition_value VARCHAR, run_id VARCHAR, built_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
    )

    full_sql: str = ctx.sql.replace("@@partition_start", f"'{date_start}'").replace(
        "@@partition_end", f"'{date_end}'"
    )

    if ctx.is_first_run:
        if ctx.on_progress is not None:
            ctx.on_progress("building all partitions")
        ctx.adapter.create_table_as(ctx.connection, target=ctx.target, sql=full_sql)
        _record_all_partitions(ctx, tracking_table, partition_col, full_sql)
        return MaterializationResult(relation=ctx.target)

    stale: list[str] = _find_stale_partitions(ctx, tracking_table, partition_col, full_sql)

    if not stale:
        if ctx.on_progress is not None:
            ctx.on_progress("no stale partitions")
        return MaterializationResult(relation=ctx.target)

    partition_value: str
    for i, partition_value in enumerate(stale):
        if ctx.on_progress is not None:
            ctx.on_progress(f"partition {i + 1}/{len(stale)}: {partition_value}")
        next_day: str = _next_date(partition_value)
        partition_sql: str = ctx.sql.replace("@@partition_start", f"'{partition_value}'").replace(
            "@@partition_end", f"'{next_day}'"
        )
        ctx.adapter.execute(
            ctx.connection,
            f"DELETE FROM {ctx.target} "
            f"WHERE CAST({partition_col} AS VARCHAR) = '{partition_value}'",
        )
        ctx.adapter.append(ctx.connection, target=ctx.target, sql=partition_sql)
        ctx.adapter.execute(
            ctx.connection,
            f"INSERT INTO {tracking_table} (partition_value, run_id) "
            f"VALUES ('{partition_value}', '{ctx.run_id}')",
        )

    return MaterializationResult(relation=ctx.target)


def _find_stale_partitions(
    ctx: MaterializationContext,
    tracking_table: str,
    partition_col: str,
    full_sql: str,
) -> list[str]:
    cursor: Any = ctx.adapter.execute(
        ctx.connection,
        f"SELECT DISTINCT CAST({partition_col} AS VARCHAR) AS pval "
        f"FROM ({full_sql}) sub "
        f"WHERE CAST({partition_col} AS VARCHAR) NOT IN "
        f"(SELECT partition_value FROM {tracking_table}) "
        f"ORDER BY pval",
    )
    return [str(row[0]) for row in cursor.fetchall()]


def _record_all_partitions(
    ctx: MaterializationContext,
    tracking_table: str,
    partition_col: str,
    full_sql: str,
) -> None:
    cursor: Any = ctx.adapter.execute(
        ctx.connection,
        f"SELECT DISTINCT CAST({partition_col} AS VARCHAR) AS pval "
        f"FROM ({full_sql}) sub ORDER BY pval",
    )
    partition_value: str
    for row in cursor.fetchall():
        partition_value = str(row[0])
        ctx.adapter.execute(
            ctx.connection,
            f"INSERT INTO {tracking_table} (partition_value, run_id) "
            f"VALUES ('{partition_value}', '{ctx.run_id}')",
        )
        if ctx.on_progress is not None:
            ctx.on_progress(f"tracked: {partition_value}")


def _next_date(date_str: str) -> str:
    parts: list[str] = date_str.split("-")
    year: int = int(parts[0])
    month: int = int(parts[1])
    day: int = int(parts[2]) + 1
    if day > 28:
        day = 1
        month += 1
    if month > 12:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}-{day:02d}"
