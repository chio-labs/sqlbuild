"""BigQuery connection wrapper."""

from typing import Any

from sqlbuild.adapters.bigquery.classes.bigquery_cursor import _BigQueryCursor


class _BigQueryConnection:
    """Small wrapper exposing an execute method for base adapter helpers."""

    def __init__(self, *, client: Any, location: str | None) -> None:
        self.client: Any = client
        self.location: str | None = location

    def execute(self, sql: str) -> _BigQueryCursor:
        job: Any = self.query_job(sql)
        return _BigQueryCursor(job.result())

    def query_job(self, sql: str) -> Any:
        return self.client.query(sql, location=self.location)

    def close(self) -> None:
        close: object | None = getattr(self.client, "close", None)
        if callable(close):
            close()
