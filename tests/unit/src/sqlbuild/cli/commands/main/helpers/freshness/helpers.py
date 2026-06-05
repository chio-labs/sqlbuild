from __future__ import annotations

from sqlbuild.adapter.shared.models import QueryResult
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind


class FreshnessRecordingAdapter:
    adapter_name: str = "freshness_test"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def supports_table_freshness_metadata(self) -> bool:
        return False

    def query(self, _connection: object, sql: str, *, limit: int | None = None) -> QueryResult:
        del limit
        self.queries.append(sql)
        if "raw_error" in sql:
            return QueryResult(columns=("left", "right"), rows=((1, 2),))
        if "raw_orders" in sql:
            return QueryResult(columns=("data_version",), rows=((1,),))
        if "raw_payments" in sql:
            return QueryResult(columns=("data_version",), rows=((2,),))
        return QueryResult(columns=("data_version",), rows=((0,),))


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
    )
