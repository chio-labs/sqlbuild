"""Each built-in adapter's warehouse statement limit and cancellation at an execution deadline."""

from __future__ import annotations

import threading

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.bigquery.classes.bigquery_connection import _BigQueryConnection
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.databricks.classes.databricks_connection import _DatabricksConnection
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.postgres.classes.postgres_connection import _PostgresConnection
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_connection import _SnowflakeConnection
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_connection import _SqlServerConnection
from sqlbuild.runtime.execution_limits.main.execution_deadline_scope import (
    execution_deadline_scope,
)
from sqlbuild.runtime.execution_limits.main.item_deadline_scope import item_deadline_scope
from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy
from sqlbuild.runtime.execution_limits.types import ItemKind
from tests.unit.src.sqlbuild.adapters._test_types import (
    BigQueryQueuedJobTestCase,
    StatementCancellationTestCase,
)
from tests.unit.src.sqlbuild.adapters.helpers import (
    BLOCKING_SQL,
    CancellableJob,
    CancellableJobClient,
    CancellableRawConnection,
    QueuedJob,
    cancel_from_watchdog,
)

_POLICY: ItemTimeoutPolicy = ItemTimeoutPolicy(limit="60s", seconds=60, source="test")
_REQUEST_ID: str = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(
    "test_case",
    [
        StatementCancellationTestCase(
            description="postgres statement_timeout in milliseconds",
            expected_limit_range=(50_000, 60_000),
            expected_asynchronous=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_deadline_when_executing_then_statement_timeout_bounds_and_cancel_stops(
    test_case: StatementCancellationTestCase,
) -> None:
    raw: CancellableRawConnection = CancellableRawConnection()
    connection: _PostgresConnection = _PostgresConnection(raw)

    with item_deadline_scope(
        kind=ItemKind.TEST, name="orders", policy=_POLICY, adapter=None, connection=connection
    ):
        cancel_from_watchdog(adapter=PostgresAdapter(), connection=connection, raw=raw)
        outside_transaction: list[str] = list(raw.executed)
        raw.executed.clear()
        _ = connection.execute("BEGIN")
        _ = connection.execute("SELECT 1")
        _ = connection.execute("ROLLBACK")
    in_transaction: list[str] = list(raw.executed)
    raw.executed.clear()
    _ = connection.execute("SELECT 1")

    assert outside_transaction == [BLOCKING_SQL]
    assert in_transaction[0] == "BEGIN"
    assert in_transaction[1].startswith("SET LOCAL statement_timeout = ")
    low, high = test_case.expected_limit_range
    assert low <= int(in_transaction[1].rsplit(" ", 1)[1]) <= high
    assert in_transaction[2:] == ["SELECT 1", "ROLLBACK"]
    assert raw.executed == ["SELECT 1"]
    assert PostgresAdapter.statement_cancellation_is_asynchronous == test_case.expected_asynchronous


@pytest.mark.parametrize(
    "test_case",
    [
        StatementCancellationTestCase(
            description="databricks STATEMENT_TIMEOUT in seconds",
            expected_limit_range=(50, 60),
            expected_asynchronous=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_databricks_deadline_when_executing_then_session_timeout_set_and_cursor_cancelled(
    test_case: StatementCancellationTestCase,
) -> None:
    raw: CancellableRawConnection = CancellableRawConnection()
    connection: _DatabricksConnection = _DatabricksConnection(raw)

    with item_deadline_scope(
        kind=ItemKind.TEST, name="orders", policy=_POLICY, adapter=None, connection=connection
    ):
        cancel_from_watchdog(adapter=DatabricksAdapter(), connection=connection, raw=raw)

    assert raw.executed[0].startswith("SET STATEMENT_TIMEOUT = ")
    low, high = test_case.expected_limit_range
    assert low <= int(raw.executed[0].rsplit(" ", 1)[1]) <= high
    assert (
        DatabricksAdapter.statement_cancellation_is_asynchronous == test_case.expected_asynchronous
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StatementCancellationTestCase(
            description="sql server driver cancel",
            expected_limit_range=(0, 0),
            expected_asynchronous=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlserver_running_statement_when_interrupted_then_driver_cancel_is_called(
    test_case: StatementCancellationTestCase,
) -> None:
    raw: CancellableRawConnection = CancellableRawConnection()
    connection: _SqlServerConnection = _SqlServerConnection(raw)

    cancel_from_watchdog(adapter=SqlServerAdapter(), connection=connection, raw=raw)

    assert raw.cursors[0].cancelled.is_set()
    assert (
        SqlServerAdapter.statement_cancellation_is_asynchronous == test_case.expected_asynchronous
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StatementCancellationTestCase(
            description="snowflake STATEMENT_TIMEOUT_IN_SECONDS and cancel request",
            expected_limit_range=(50, 60),
            expected_asynchronous=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_running_statement_when_interrupted_then_cancel_request_names_it(
    test_case: StatementCancellationTestCase,
) -> None:
    raw: CancellableRawConnection = CancellableRawConnection()
    connection: _SnowflakeConnection = _SnowflakeConnection(raw)

    with item_deadline_scope(
        kind=ItemKind.TEST, name="orders", policy=_POLICY, adapter=None, connection=connection
    ):
        cancel_from_watchdog(adapter=SnowflakeAdapter(), connection=connection, raw=raw)

    assert raw.cancel_requests == [("SELECT * FROM orders", _REQUEST_ID)]
    statement_params: dict[str, str] | None = raw.cursors[0].statement_params
    assert statement_params is not None
    low, high = test_case.expected_limit_range
    assert low <= int(statement_params["STATEMENT_TIMEOUT_IN_SECONDS"]) <= high
    assert (
        SnowflakeAdapter.statement_cancellation_is_asynchronous == test_case.expected_asynchronous
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StatementCancellationTestCase(
            description="bigquery job timeout and jobs.cancel",
            expected_limit_range=(50_000, 60_000),
            expected_asynchronous=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bigquery_deadline_when_executing_then_job_timeout_set_and_job_cancelled(
    test_case: StatementCancellationTestCase,
) -> None:
    client: CancellableJobClient = CancellableJobClient()
    connection: _BigQueryConnection = _BigQueryConnection(client=client, location=None)
    adapter: BigQueryAdapter = BigQueryAdapter()
    blocking_job: CancellableJob = CancellableJob()
    client.job = blocking_job

    def watchdog() -> None:
        assert blocking_job.waiting.wait(timeout=5)
        assert adapter.interrupt_connection(connection) is True

    thread: threading.Thread = threading.Thread(target=watchdog)
    with item_deadline_scope(
        kind=ItemKind.TEST, name="orders", policy=_POLICY, adapter=None, connection=connection
    ):
        thread.start()
        with pytest.raises(RuntimeError, match="statement cancelled"):
            _ = connection.execute("SELECT * FROM orders")
    thread.join(timeout=5)
    client.job = QueuedJob(pending_polls=0, poll_seconds=0.0)
    with execution_deadline_scope(
        max_duration_seconds=60, max_duration="60s", target_name="dev", remediation=None
    ):
        _ = connection.execute("SELECT * FROM orders")

    low, high = test_case.expected_limit_range
    assert client.job_configs[0] is None
    assert low <= int(client.job_configs[1].job_timeout_ms) <= high
    assert BigQueryAdapter.statement_cancellation_is_asynchronous == test_case.expected_asynchronous


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryQueuedJobTestCase(
            description="queued job time is excluded from the item running time",
            pending_polls=8,
            poll_seconds=0.05,
            expected_maximum_running_seconds=0.2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_queued_bigquery_job_when_waiting_then_item_clock_is_stopped(
    test_case: BigQueryQueuedJobTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    client: CancellableJobClient = CancellableJobClient()
    client.job = QueuedJob(pending_polls=test_case.pending_polls, poll_seconds=0.0)
    connection: _BigQueryConnection = _BigQueryConnection(client=client, location=None)
    monkeypatch.setattr(
        "sqlbuild.adapters.bigquery.classes.bigquery_connection.PENDING_JOB_POLL_SECONDS",
        test_case.poll_seconds,
    )

    with item_deadline_scope(
        kind=ItemKind.TEST, name="orders", policy=_POLICY, adapter=None, connection=connection
    ) as deadline:
        _ = connection.execute("SELECT * FROM orders")
        assert deadline is not None
        running: float = deadline.running_seconds()

    assert client.job_configs == [None]
    assert running < test_case.expected_maximum_running_seconds


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
