"""BigQuery connection wrapper."""

from typing import Any

from sqlbuild.adapters.bigquery._helpers.statement_telemetry import affected_rows
from sqlbuild.adapters.bigquery.classes.bigquery_cursor import _BigQueryCursor
from sqlbuild.adapters.bigquery.constants import SELECT_STATEMENT_TYPE
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle


class _BigQueryConnection:
    """Small wrapper exposing an execute method for base adapter helpers."""

    def __init__(self, *, client: Any, location: str | None) -> None:
        self.client: Any = client
        self.location: str | None = location

    def execute(self, sql: str) -> _BigQueryCursor:
        with StatementLifecycle(adapter="bigquery", sql=sql, intent="execute") as lifecycle:
            job: Any = self.query_job(sql)
            job_id: str | None = _job_id(job=job)
            lifecycle.submitted(job_id=job_id)
            try:
                cursor: _BigQueryCursor = _BigQueryCursor(job.result())
            except Exception as error:
                lifecycle.failed(error=error, job_id=job_id)
                raise
            statement_type: object | None = getattr(job, "statement_type", None)
            dml_affected_rows: int | None = affected_rows(job=job)
            if statement_type == SELECT_STATEMENT_TYPE:
                lifecycle.completed(job_id=job_id, row_count=len(cursor._rows))
            else:
                lifecycle.completed(job_id=job_id, affected_rows=dml_affected_rows)
            return cursor

    def query_job(self, sql: str) -> Any:
        return self.client.query(sql, location=self.location)

    def close(self) -> None:
        close: object | None = getattr(self.client, "close", None)
        if callable(close):
            close()


def _job_id(*, job: Any) -> str | None:
    value: object | None = getattr(job, "job_id", None)
    return value if isinstance(value, str) and value else None
