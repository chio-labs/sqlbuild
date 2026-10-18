"""Shared fakes for adapter unit tests."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest


class FetchedRows:
    """A cursor result that returns fixed rows."""

    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self._rows: list[tuple[str, str]] = rows

    def fetchall(self) -> list[tuple[str, str]]:
        """Return the fixed rows."""

        return self._rows


def recording_execute(
    *, rows: list[tuple[str, str]], executed: list[str]
) -> Callable[..., FetchedRows]:
    """Return an adapter execute stub that records SQL and returns fixed rows."""

    def execute(*, connection: Any, sql: str) -> FetchedRows:
        del connection
        executed.append(sql)
        return FetchedRows(rows)

    return execute


class GrantRows:
    """A cursor result that returns fixed grant rows of any width."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows: list[tuple[object, ...]] = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        """Return the fixed rows."""

        return self._rows


class GrantConnection:
    """A connection that records SQL, answers queries in order, and names a project."""

    def __init__(self, answers: tuple[list[tuple[object, ...]], ...]) -> None:
        self.answers: Iterator[list[tuple[object, ...]]] = iter(answers)
        self.executed: list[str] = []
        self.location: str = "US"
        self.client: GrantClient = GrantClient()

    def execute(self, sql: str) -> GrantRows:
        """Record the SQL and return the next answer, or no rows once they run out."""

        self.executed.append(sql)
        return GrantRows(next(self.answers, []))


class GrantClient:
    """The BigQuery client attribute of a fake connection."""

    project: str = "orders-project"


def grant_execute(connection: GrantConnection) -> Callable[..., GrantRows]:
    """Return an adapter execute stub that routes SQL to a recording connection."""

    def execute(*, connection: Any, sql: str) -> GrantRows:
        return connection.execute(sql)

    del connection
    return execute


class MetadataCursor:
    """A cursor that records metadata SQL and returns fixed rows."""

    def __init__(self, *, rows: tuple[tuple[object, ...], ...], executed: list[str]) -> None:
        self._rows: tuple[tuple[object, ...], ...] = rows
        self._executed: list[str] = executed

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> MetadataCursor:
        self._executed.append(f"{sql} {params or ()}")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return next(iter(self._rows), None)

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self._rows)

    def close(self) -> None:
        return None


class MetadataConnection:
    """A connection whose cursors share one SQL log and fixed rows."""

    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.rows: tuple[tuple[object, ...], ...] = rows
        self.executed: list[str] = []

    def cursor(self) -> MetadataCursor:
        return MetadataCursor(rows=self.rows, executed=self.executed)


@dataclass(frozen=True)
class FakeBigQueryTable:
    """BigQuery tables API metadata."""

    table_type: str
    num_rows: int | None


class FakeBigQueryClient:
    """BigQuery client that records requested table ids."""

    def __init__(self, table: FakeBigQueryTable) -> None:
        self.table: FakeBigQueryTable = table
        self.requested: list[str] = []

    def get_table(self, table_id: str) -> FakeBigQueryTable:
        self.requested.append(table_id)
        return self.table


@dataclass(frozen=True)
class FakeBigQueryConnection:
    """BigQuery connection holding a fake client."""

    client: FakeBigQueryClient


def execute_through_cursor(*, connection: MetadataConnection, sql: str) -> MetadataCursor:
    """Adapter execute stub that runs SQL on a fresh fake cursor."""

    return connection.cursor().execute(sql)


BLOCKING_SQL: str = "SELECT * FROM orders"


class BlockingCursor:
    """A DB-API cursor whose query blocks until another thread cancels it."""

    def __init__(self, *, executed: list[str], started: threading.Event) -> None:
        self.executed: list[str] = executed
        self.started: threading.Event = started
        self.cancelled: threading.Event = threading.Event()
        self.connection: object | None = None
        self.description: object | None = None
        self.rowcount: int = -1
        self._request_id: str = "11111111-1111-4111-8111-111111111111"
        self.sfqid: str | None = None
        self.statement_params: dict[str, str] | None = None

    def execute(self, sql: str, *args: Any, **kwargs: Any) -> BlockingCursor:
        del args
        self.executed.append(sql)
        self.statement_params = kwargs.get("_statement_params")
        responses: dict[bool, Callable[[], BlockingCursor]] = {
            True: self._block_until_cancelled,
            False: lambda: self,
        }
        return responses[sql == BLOCKING_SQL]()

    def _block_until_cancelled(self) -> BlockingCursor:
        self.started.set()
        assert self.cancelled.wait(timeout=5), "statement was not cancelled"
        raise RuntimeError("statement cancelled")

    def cancel(self) -> None:
        self.cancelled.set()

    def close(self) -> None:
        return None


class CancellableRawConnection:
    """A raw driver connection exposing each driver's cancel entry point."""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.cursors: list[BlockingCursor] = []
        self.cancel_requests: list[tuple[str, str]] = []
        self.started: threading.Event = threading.Event()
        self._conn: CancellableRawConnection = self

    def cursor(self) -> BlockingCursor:
        cursor: BlockingCursor = BlockingCursor(executed=self.executed, started=self.started)
        cursor.connection = self
        self.cursors.append(cursor)
        return cursor

    def execute(self, sql: str) -> None:
        self.executed.append(sql)

    def cancel_safe(self) -> None:
        self._cancel_running()

    def cancel(self) -> None:
        self._cancel_running()

    def _cancel_query(self, sql: str, request_id: str) -> dict[str, bool]:
        self.cancel_requests.append((sql, request_id))
        self._cancel_running()
        return {"success": True}

    def _cancel_running(self) -> None:
        for cursor in self.cursors:
            cursor.cancel()


def cancel_from_watchdog(*, adapter: Any, connection: Any, raw: CancellableRawConnection) -> None:
    """Run a blocking query while another thread asks the adapter to cancel it."""

    def watchdog() -> None:
        assert raw.started.wait(timeout=5)
        assert adapter.interrupt_connection(connection) is True

    thread: threading.Thread = threading.Thread(target=watchdog)
    thread.start()
    with pytest.raises(RuntimeError, match="statement cancelled"):
        connection.execute(BLOCKING_SQL)
    thread.join(timeout=5)


class CancellableJob:
    """A BigQuery job whose result blocks until it is cancelled."""

    def __init__(self) -> None:
        self.job_id: str = "job-1"
        self.cancelled: threading.Event = threading.Event()
        self.waiting: threading.Event = threading.Event()

    def result(self) -> list[object]:
        self.waiting.set()
        assert self.cancelled.wait(timeout=5), "job was not cancelled"
        raise RuntimeError("statement cancelled")

    def cancel(self) -> bool:
        self.cancelled.set()
        return True


class CancellableJobClient:
    """A BigQuery client returning one cancellable job and recording each job config."""

    def __init__(self) -> None:
        self.job: CancellableJob = CancellableJob()
        self.job_configs: list[Any] = []

    def query(self, sql: str, **kwargs: Any) -> CancellableJob:
        del sql
        self.job_configs.append(kwargs.get("job_config"))
        return self.job
