"""Helpers for ClickHouse adapter unit tests."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.models import RelationInfo, RelationUsageReport
from sqlbuild.adapters.clickhouse._helpers.type_text import quote_string
from sqlbuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter


class FakeQueryLogError(Exception):
    """A ClickHouse server error carrying its code in the message, as clickhouse-connect does."""

    @classmethod
    def raised(cls, message: str) -> tuple[Exception, ...]:
        """The error as the only one a fake connection raises."""

        return (cls(message),)


class FakeQueryLogCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows: list[tuple[object, ...]] = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class FakeQueryLogConnection:
    """Answers the log_queries setting and query_log reads, recording each query_log read."""

    def __init__(
        self,
        *,
        rows: tuple[tuple[object, ...], ...] = (),
        log_queries: object = True,
        errors: tuple[Exception, ...] = (),
        replicas: int = 1,
    ) -> None:
        self.rows: tuple[tuple[object, ...], ...] = rows
        self.log_queries: object = log_queries
        self.errors: tuple[Exception, ...] = errors
        self.replicas: int = replicas
        self.queries: list[str] = []

    def execute(self, sql: str) -> FakeQueryLogCursor:
        reads: dict[tuple[bool, bool], Callable[[], FakeQueryLogCursor]] = {
            (True, False): lambda: FakeQueryLogCursor([(self.log_queries,)]),
            (False, True): lambda: FakeQueryLogCursor([(self.replicas,)]),
            (False, False): lambda: self.query_log_rows(sql),
        }
        return reads[(sql == "SELECT getSetting('log_queries')", "system.clusters" in sql)]()

    def query_log_rows(self, sql: str) -> FakeQueryLogCursor:
        self.queries.append(sql)
        error: Exception
        for error in self.errors:
            raise error
        return FakeQueryLogCursor(
            list(filter(lambda row: quote_string(str(row[0])) in sql.split(" IN (")[-1], self.rows))
        )


def usage_relation(schema: str, name: str) -> RelationInfo:
    """A ClickHouse table, whose database is its schema."""

    return RelationInfo(database=None, schema=schema, name=name, relation_type="BASE TABLE")


def read_clickhouse_usage(
    *, connection: FakeQueryLogConnection, relations: tuple[RelationInfo, ...], window_seconds: int
) -> RelationUsageReport:
    """ClickHouse's usage report for the relations from the fake connection."""

    return ClickHouseAdapter().relation_usage(
        connection=connection, relations=relations, window_seconds=window_seconds
    )
