"""BigQuery connection wrapper."""

import math
import threading
import time
from typing import Any

from sqlbuild.adapters.bigquery._helpers.statement_telemetry import affected_rows
from sqlbuild.adapters.bigquery.classes.bigquery_cursor import _BigQueryCursor
from sqlbuild.adapters.bigquery.constants import (
    PENDING_JOB_POLL_SECONDS,
    PENDING_JOB_STATE,
    SELECT_STATEMENT_TYPE,
)
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.main.current_build_deadline import current_build_deadline
from sqlbuild.runtime.execution_limits.main.current_execution_deadline import (
    current_execution_deadline,
)
from sqlbuild.runtime.execution_limits.main.current_item_deadline import current_item_deadline
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle


class _BigQueryConnection:
    """Small wrapper exposing an execute method for base adapter helpers."""

    def __init__(self, *, client: Any, location: str | None) -> None:
        self.client: Any = client
        self.location: str | None = location
        self._active_jobs: dict[int, Any] = {}
        self._jobs_lock: threading.Lock = threading.Lock()

    def execute(self, sql: str) -> _BigQueryCursor:
        with StatementLifecycle(adapter="bigquery", sql=sql, intent="execute") as lifecycle:
            job: Any = self.query_job(sql)
            job_id: str | None = _job_id(job=job)
            lifecycle.submitted(job_id=job_id)
            try:
                cursor: _BigQueryCursor = _BigQueryCursor(self.job_result(job))
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
        """Submit a job; only the whole-build limit becomes a job timeout, as it counts queueing."""

        deadline: ExecutionDeadline | ItemDeadline | None = current_execution_deadline()
        if deadline is not None:
            deadline.enforce()
        build: ExecutionDeadline | None = current_build_deadline()
        if build is None:
            return self.client.query(sql, location=self.location)
        from google.cloud import bigquery

        return self.client.query(
            sql,
            location=self.location,
            job_config=bigquery.QueryJobConfig(
                job_timeout_ms=max(1, math.ceil(build.remaining_seconds * 1000))
            ),
        )

    def job_result(self, job: Any) -> Any:
        """Wait for a job while it is registered for cancellation at a deadline."""

        with self._jobs_lock:
            self._active_jobs[id(job)] = job
        try:
            _wait_while_pending(job=job, deadline=current_item_deadline())
            return job.result()
        finally:
            with self._jobs_lock:
                self._active_jobs.pop(id(job), None)

    def cancel_active_jobs(self) -> None:
        """Request cancellation of every job this connection is waiting on."""

        with self._jobs_lock:
            jobs: list[Any] = list(self._active_jobs.values())
        for job in jobs:
            job.cancel()

    def close(self) -> None:
        close: object | None = getattr(self.client, "close", None)
        if callable(close):
            close()


def _wait_while_pending(*, job: Any, deadline: ItemDeadline | None) -> None:
    """Stop an item's clock while its job waits in a queue, so only running time counts."""

    if deadline is None or getattr(job, "state", None) != PENDING_JOB_STATE:
        return
    deadline.statement_queued()
    try:
        while getattr(job, "state", None) == PENDING_JOB_STATE:
            time.sleep(PENDING_JOB_POLL_SECONDS)
            job.reload()
    finally:
        deadline.statement_dequeued()


def _job_id(*, job: Any) -> str | None:
    value: object | None = getattr(job, "job_id", None)
    return value if isinstance(value, str) and value else None
