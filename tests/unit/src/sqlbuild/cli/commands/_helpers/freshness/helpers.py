from __future__ import annotations

from datetime import datetime

from sqlbuild.adapter.models import (
    QueryResult,
    TableFreshnessMetadata,
    TableFreshnessRequest,
)
from sqlbuild.compiler.source_freshness.main.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord
from sqlbuild.spec.contracts.models import (
    SourceEntry,
    SourceFreshnessAgePolicy,
    SourceFreshnessConfig,
)
from sqlbuild.spec.contracts.types import SourceFreshnessStrategy, SourceFreshnessValueKind


class FreshnessRecordingAdapter:
    adapter_name: str = "freshness_test"

    def __init__(self, *, table_metadata_supported: bool = False) -> None:
        self.queries: list[str] = []
        self.metadata_requests: list[tuple[str | None, str | None, str]] = []
        self.table_metadata_supported: bool = table_metadata_supported

    def supports_table_freshness_metadata(self) -> bool:
        return self.table_metadata_supported

    def get_table_freshness_metadata(
        self,
        *,
        connection: object,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> TableFreshnessMetadata:
        del connection
        self.metadata_requests.append((database, schema, name))
        return TableFreshnessMetadata(
            data_version=datetime(2026, 1, 2, 3, 4, 5),
            value_kind="timestamp",
            observed_at=datetime(2026, 1, 2, 3, 5, 0),
        )

    def get_tables_freshness_metadata(
        self,
        *,
        connection: object,
        requests: tuple[TableFreshnessRequest, ...],
    ) -> dict[TableFreshnessRequest, TableFreshnessMetadata]:
        return {
            request: self.get_table_freshness_metadata(
                connection=connection,
                database=request.database,
                schema=request.schema,
                name=request.name,
            )
            for request in requests
        }

    def query(self, *, connection: object, sql: str, limit: int | None = None) -> QueryResult:
        del connection, limit
        self.queries.append(sql)
        results_by_sql: dict[str, QueryResult] = {
            "SELECT 1 AS left, 2 AS right FROM raw_error": QueryResult(
                columns=("left", "right"), rows=((1, 2),)
            ),
            "SELECT 1 AS data_version FROM raw_orders": QueryResult(
                columns=("data_version",), rows=((1,),)
            ),
            "SELECT 2 AS data_version FROM raw_payments": QueryResult(
                columns=("data_version",), rows=((2,),)
            ),
            "SELECT TIMESTAMP '2026-01-01 00:05:00' AS data_version FROM raw_lag": QueryResult(
                columns=("data_version",),
                rows=((datetime(2026, 1, 1, 0, 5, 0),),),
            ),
            (
                "SELECT TIMESTAMP '2025-12-31 21:00:00' AS data_version FROM raw_age_error"
            ): QueryResult(
                columns=("data_version",),
                rows=((datetime(2025, 12, 31, 21, 0, 0),),),
            ),
            "SELECT TIMESTAMP '2025-12-31 22:30:00' AS data_version FROM raw_age_warn": QueryResult(
                columns=("data_version",),
                rows=((datetime(2025, 12, 31, 22, 30, 0),),),
            ),
            "SELECT TIMESTAMP '2025-12-31 23:30:00' AS data_version FROM raw_age_pass": QueryResult(
                columns=("data_version",),
                rows=((datetime(2025, 12, 31, 23, 30, 0),),),
            ),
            "SELECT 42 AS data_version FROM raw_age_unknown": QueryResult(
                columns=("data_version",), rows=((42,),)
            ),
        }
        return results_by_sql[sql]


def freshness_sources() -> tuple[SourceEntry, ...]:
    return (
        SourceEntry(
            name="raw_orders",
            expression="SELECT 1 AS order_id",
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.SQL,
                value_kind=SourceFreshnessValueKind.INTEGER,
                query="SELECT 1 AS data_version FROM raw_orders",
            ),
        ),
        SourceEntry(
            name="raw_payments",
            expression="SELECT 2 AS payment_id",
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.SQL,
                value_kind=SourceFreshnessValueKind.INTEGER,
                query="SELECT 2 AS data_version FROM raw_payments",
            ),
        ),
        SourceEntry(
            name="raw_error",
            expression="SELECT 3 AS event_id",
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.SQL,
                value_kind=SourceFreshnessValueKind.INTEGER,
                query="SELECT 1 AS left, 2 AS right FROM raw_error",
            ),
        ),
        SourceEntry(name="raw_unknown", expression="SELECT 4 AS event_id"),
        SourceEntry(
            name="raw_lag",
            expression="SELECT 5 AS event_id",
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.SQL,
                value_kind=SourceFreshnessValueKind.TIMESTAMP,
                query="SELECT TIMESTAMP '2026-01-01 00:05:00' AS data_version FROM raw_lag",
                lag_tolerance="10m",
            ),
        ),
        SourceEntry(
            name="raw_age_error",
            expression="SELECT 6 AS event_id",
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.SQL,
                value_kind=SourceFreshnessValueKind.TIMESTAMP,
                query="SELECT TIMESTAMP '2025-12-31 21:00:00' AS data_version FROM raw_age_error",
                age_policy=SourceFreshnessAgePolicy(warn_after="1h", error_after="2h"),
            ),
        ),
        SourceEntry(
            name="raw_age_warn",
            expression="SELECT 7 AS event_id",
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.SQL,
                value_kind=SourceFreshnessValueKind.TIMESTAMP,
                query="SELECT TIMESTAMP '2025-12-31 22:30:00' AS data_version FROM raw_age_warn",
                age_policy=SourceFreshnessAgePolicy(warn_after="1h", error_after="2h"),
            ),
        ),
        SourceEntry(
            name="raw_age_pass",
            expression="SELECT 8 AS event_id",
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.SQL,
                value_kind=SourceFreshnessValueKind.TIMESTAMP,
                query="SELECT TIMESTAMP '2025-12-31 23:30:00' AS data_version FROM raw_age_pass",
                age_policy=SourceFreshnessAgePolicy(warn_after="1h", error_after="2h"),
            ),
        ),
        SourceEntry(
            name="raw_age_unknown",
            expression="SELECT 9 AS event_id",
            freshness=SourceFreshnessConfig(
                strategy=SourceFreshnessStrategy.SQL,
                value_kind=SourceFreshnessValueKind.INTEGER,
                query="SELECT 42 AS data_version FROM raw_age_unknown",
                age_policy=SourceFreshnessAgePolicy(warn_after="1h", error_after="2h"),
            ),
        ),
    )


def adapter_metadata_sources() -> tuple[SourceEntry, ...]:
    return (
        SourceEntry(
            name="raw_metadata",
            database="analytics",
            schema="raw",
            table="orders",
        ),
    )


def source_freshness_record(
    *,
    source_name: str,
    value_kind: str = "integer",
    data_version: str = "1",
    data_version_hash: str | None = None,
) -> SourceFreshnessRecord:
    return SourceFreshnessRecord(
        source_name=source_name,
        target_database=None,
        target_schema=None,
        target_name=None,
        run_id="previous",
        strategy="sql",
        value_kind=value_kind,
        data_version=data_version,
        data_version_hash=data_version_hash
        or source_freshness_data_version_hash(
            source_name=source_name,
            strategy="sql",
            value_kind=value_kind,
            data_version=data_version,
        ),
        observed_at=datetime(2025, 12, 31, 0, 0, 0),
    )
