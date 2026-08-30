from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Any

import pytest

from sqlbuild.adapters.snowflake.classes.snowflake_connection import _SnowflakeConnection
from sqlbuild.adapters.snowflake.classes.snowflake_cursor import _SnowflakeCursor
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.constants import COST_TELEMETRY_HEALTH
from sqlbuild.cost.models import StatementExecutionTelemetry
from tests.unit.src.sqlbuild.adapters.snowflake.classes.snowflake_connection._test_types import (
    CursorAttributeTestCase,
    CursorContextManagerTestCase,
    CursorIterationTestCase,
    CursorReturnTestCase,
    QueryTagPolicyTestCase,
    SnowflakeConnectionTestCase,
    StatementDiagnosticsTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.classes.snowflake_connection.helpers import (
    read_ledger,
)


class _Cursor:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        rows: tuple[tuple[object, ...], ...] = (),
        suppress_exceptions: bool = False,
    ) -> None:
        self.error = error
        self.rows = rows
        self.suppress_exceptions = suppress_exceptions
        self.sfqid: str | None = None
        self.statement_params: dict[str, str] | None = None
        self.closed = False
        self.calls = 0
        self.arraysize = 1

    def execute(self, sql: str, *, _statement_params: dict[str, str] | None = None) -> _Cursor:
        self.calls += 1
        self.statement_params = _statement_params
        if self.error is not None:
            raise self.error
        self.sfqid = "01c-query-id"
        return self

    def executemany(
        self,
        sql: str,
        rows: list[tuple[object, ...]],
        *,
        _statement_params: dict[str, str] | None = None,
    ) -> _Cursor:
        del sql, rows
        self.statement_params = _statement_params
        self.sfqid = "01c-query-id"
        return self

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, exc_value, traceback
        self.closed = True
        return self.suppress_exceptions

    def __iter__(self) -> Iterator[tuple[object, ...]]:
        return iter(self.rows)


class _RawConnection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor


class _QueryTagRejectingCursor(_Cursor):
    def __init__(self) -> None:
        super().__init__()
        self.sfqid = None
        self.calls = 0

    def execute(self, sql: str, *, _statement_params: dict[str, str] | None = None) -> _Cursor:
        self.calls += 1
        self.statement_params = _statement_params
        if _statement_params is not None and "QUERY_TAG" in _statement_params:
            raise RuntimeError("unsupported statement parameter QUERY_TAG")
        self.sfqid = "01c-fallback-query-id"
        return self


class _StaleQueryTagRejectingCursor(_QueryTagRejectingCursor):
    def __init__(self) -> None:
        super().__init__()
        self.sfqid = "01c-previous-query-id"


class _SubmittedQueryTagErrorCursor(_Cursor):
    def __init__(self) -> None:
        super().__init__()
        self.sfqid = "01c-previous-query-id"
        self.calls: int = 0

    def execute(self, sql: str, *, _statement_params: dict[str, str] | None = None) -> _Cursor:
        del sql, _statement_params
        self.calls += 1
        self.sfqid = "01c-submitted-query-id"
        raise RuntimeError("submitted QUERY_TAG statement failed")


@pytest.mark.parametrize(
    "test_case",
    [
        StatementDiagnosticsTestCase(
            description="completed statement reports query identity and elapsed time",
            expected_query_id="01c-query-id",
            expected_status="success",
            expected_resource_type="model",
            expected_resource_name="orders",
            expected_phase="materialize",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_statement_callback_when_query_completes_then_reports_resource_diagnostics(
    test_case: StatementDiagnosticsTestCase,
    tmp_path: Path,
) -> None:
    telemetry: list[StatementExecutionTelemetry] = []
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(_Cursor()))

    with CostContext.scope(
        run_id="diagnostic-run",
        resource_type=test_case.expected_resource_type,
        resource_name=test_case.expected_resource_name,
        phase=test_case.expected_phase,
        ledger_path=tmp_path / "statements.jsonl",
        on_statement_complete=telemetry.append,
    ):
        connection.execute("SELECT 1")

    assert len(telemetry) == 1
    assert telemetry[0].query_id == test_case.expected_query_id
    assert telemetry[0].status == test_case.expected_status
    assert telemetry[0].resource_type == test_case.expected_resource_type
    assert telemetry[0].resource_name == test_case.expected_resource_name
    assert telemetry[0].phase == test_case.expected_phase
    assert telemetry[0].elapsed_seconds >= 0


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeConnectionTestCase(
            description="diagnostic callback failure does not affect completed query",
            expected_query_id="01c-query-id",
            expected_status="success",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_statement_callback_when_query_completes_then_result_is_unchanged(
    test_case: SnowflakeConnectionTestCase,
    tmp_path: Path,
) -> None:
    cursor: _Cursor = _Cursor()
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))

    def fail_diagnostics(_telemetry: StatementExecutionTelemetry) -> None:
        raise RuntimeError("diagnostic sink unavailable")

    with CostContext.scope(
        run_id="diagnostic-failure-run",
        resource_type="model",
        resource_name="orders",
        ledger_path=tmp_path / "statements.jsonl",
        on_statement_complete=fail_diagnostics,
    ):
        result: Any = connection.execute("SELECT 1")

    assert result.raw_cursor is cursor
    assert cursor.sfqid == test_case.expected_query_id


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeConnectionTestCase(
            description="successful tagged statement persists query ID",
            expected_query_id="01c-query-id",
            expected_status="success",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_successful_tagged_statement_when_executing_then_query_id_is_persisted(
    test_case: SnowflakeConnectionTestCase,
    tmp_path: Path,
) -> None:
    cursor: _Cursor = _Cursor()
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    ledger_path: Path = tmp_path / "statements.jsonl"

    with CostContext.scope(
        run_id="run-1",
        resource_type="model",
        resource_name="orders",
        ledger_path=ledger_path,
    ):
        result: Any = connection.execute("SELECT 1")

    assert result.raw_cursor is cursor
    assert cursor.statement_params is not None
    tag_payload: dict[str, object] = json.loads(cursor.statement_params["QUERY_TAG"])
    statement_id: object = tag_payload.pop("statement_id")
    assert isinstance(statement_id, str)
    assert len(statement_id) == 32
    assert tag_payload == {
        "app": "sqlbuild",
        "attempt": 1,
        "phase": "execute",
        "resource_name": "orders",
        "resource_type": "model",
        "run_id": "run-1",
        "v": 1,
    }
    payload: dict[str, Any] = read_ledger(ledger_path)
    assert payload["query_id"] == test_case.expected_query_id
    assert payload["status"] == test_case.expected_status
    assert payload["statement_id"] == statement_id
    assert payload["resource_name"] == "orders"
    assert "SELECT 1" not in ledger_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeConnectionTestCase(
            description="failed tagged statement persists query ID",
            expected_query_id=None,
            expected_status="failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failed_tagged_statement_when_executing_then_failure_query_id_is_persisted(
    test_case: SnowflakeConnectionTestCase,
    tmp_path: Path,
) -> None:
    cursor: _Cursor = _Cursor(error=RuntimeError("warehouse statement failed"))
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    ledger_path: Path = tmp_path / "statements.jsonl"

    with pytest.raises(RuntimeError, match="warehouse statement failed"):
        with CostContext.scope(
            run_id="run-1",
            resource_type="model",
            resource_name="orders",
            ledger_path=ledger_path,
        ):
            connection.execute("SELECT invalid")

    payload: dict[str, Any] = read_ledger(ledger_path)
    assert payload["query_id"] == test_case.expected_query_id
    assert payload["status"] == test_case.expected_status
    assert payload["error_type"] == "RuntimeError"
    assert "error_message" not in payload


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeConnectionTestCase(
            description="rejected tag retries and persists fallback query ID",
            expected_query_id="01c-fallback-query-id",
            expected_status="success",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_tag_rejected_before_submission_when_executing_then_statement_runs_untagged(
    test_case: SnowflakeConnectionTestCase,
    tmp_path: Path,
) -> None:
    cursor: _QueryTagRejectingCursor = _QueryTagRejectingCursor()
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    ledger_path: Path = tmp_path / "statements.jsonl"

    with CostContext.scope(
        run_id="run-1",
        resource_type="model",
        resource_name="orders",
        ledger_path=ledger_path,
    ):
        result: Any = connection.execute("SELECT 1")

    assert result.raw_cursor is cursor
    assert cursor.calls == 2
    assert cursor.statement_params is None
    payload: dict[str, Any] = read_ledger(ledger_path)
    assert payload["query_id"] == test_case.expected_query_id
    assert payload["status"] == test_case.expected_status


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeConnectionTestCase(
            description="stale query ID does not block safe pre-submission fallback",
            expected_query_id="01c-fallback-query-id",
            expected_status="success",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_stale_query_id_and_rejected_tag_when_executing_then_untagged_fallback_runs(
    test_case: SnowflakeConnectionTestCase,
    tmp_path: Path,
) -> None:
    cursor: _StaleQueryTagRejectingCursor = _StaleQueryTagRejectingCursor()
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    ledger_path: Path = tmp_path / "statements.jsonl"

    with CostContext.scope(
        run_id="run-1",
        resource_type="model",
        resource_name="orders",
        ledger_path=ledger_path,
    ):
        connection.execute("SELECT 1")

    payload: dict[str, Any] = read_ledger(ledger_path)
    assert cursor.calls == 2
    assert payload["query_id"] == test_case.expected_query_id
    assert payload["status"] == test_case.expected_status


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeConnectionTestCase(
            description="assigned query ID prevents retry after submitted failure",
            expected_query_id="01c-submitted-query-id",
            expected_status="failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_submitted_query_id_when_statement_fails_then_user_sql_is_not_retried(
    test_case: SnowflakeConnectionTestCase,
    tmp_path: Path,
) -> None:
    cursor: _SubmittedQueryTagErrorCursor = _SubmittedQueryTagErrorCursor()
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    ledger_path: Path = tmp_path / "statements.jsonl"

    with pytest.raises(RuntimeError, match="submitted QUERY_TAG statement failed"):
        with CostContext.scope(
            run_id="run-1",
            resource_type="model",
            resource_name="orders",
            ledger_path=ledger_path,
        ):
            connection.execute("SELECT invalid")

    payload: dict[str, Any] = read_ledger(ledger_path)
    assert cursor.calls == 1
    assert payload["query_id"] == test_case.expected_query_id
    assert payload["status"] == test_case.expected_status


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeConnectionTestCase(
            description="ledger write failure does not interrupt submitted statement",
            expected_query_id="01c-query-id",
            expected_status="success",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ledger_write_failure_when_executing_then_statement_result_is_unchanged(
    test_case: SnowflakeConnectionTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor: _Cursor = _Cursor()
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    ledger_path: Path = tmp_path / "statements.jsonl"

    def fail_append(**kwargs: Any) -> None:
        del kwargs
        raise OSError("disk unavailable")

    monkeypatch.setattr("sqlbuild.cost._helpers.ledger._append_statement", fail_append)
    with CostContext.scope(
        run_id="ledger-failure-run",
        resource_type="model",
        resource_name="orders",
        ledger_path=ledger_path,
    ):
        result: Any = connection.execute("SELECT 1")

    assert result.raw_cursor is cursor
    assert cursor.sfqid == test_case.expected_query_id
    assert test_case.expected_status == "success"
    assert not ledger_path.exists()
    assert COST_TELEMETRY_HEALTH.consume_ledger_failure(run_id="ledger-failure-run") == "OSError"


@pytest.mark.parametrize(
    "test_case",
    [
        CursorReturnTestCase(
            description="execute and executemany return the instrumented proxy",
            expected_execute_is_proxy=True,
            expected_executemany_is_proxy=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_returning_operations_when_executing_then_proxy_is_returned(
    test_case: CursorReturnTestCase,
) -> None:
    cursor: _Cursor = _Cursor()
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    proxy: _SnowflakeCursor = connection.cursor()

    execute_result: Any = proxy.execute("SELECT 1")
    executemany_result: Any = proxy.executemany("INSERT INTO t VALUES (?)", [(1,)])

    assert (execute_result is proxy) is test_case.expected_execute_is_proxy
    assert (executemany_result is proxy) is test_case.expected_executemany_is_proxy


@pytest.mark.parametrize(
    "test_case",
    [
        CursorContextManagerTestCase(
            description="proxy delegates exit and preserves exception suppression",
            suppress_exceptions=True,
            expected_closed=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_context_manager_when_entering_then_proxy_and_exit_semantics_are_preserved(
    test_case: CursorContextManagerTestCase,
) -> None:
    cursor: _Cursor = _Cursor(suppress_exceptions=test_case.suppress_exceptions)
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    proxy: _SnowflakeCursor = connection.cursor()

    with proxy as entered:
        assert entered is proxy
        raise RuntimeError("suppressed by raw cursor")

    assert cursor.closed is test_case.expected_closed


@pytest.mark.parametrize(
    "test_case",
    [
        CursorIterationTestCase(
            description="proxy iteration delegates to raw cursor rows",
            rows=((1, "one"), (2, "two")),
            expected_rows=((1, "one"), (2, "two")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_iterable_cursor_when_iterating_then_raw_rows_are_returned(
    test_case: CursorIterationTestCase,
) -> None:
    cursor: _Cursor = _Cursor(rows=test_case.rows)
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))

    rows: list[tuple[object, ...]] = list(connection.cursor())

    assert rows == list(test_case.expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorAttributeTestCase(
            description="proxy writes mutable DB-API attributes to raw cursor",
            arraysize=50,
            expected_arraysize=50,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_writable_cursor_attribute_when_assigning_then_raw_cursor_is_updated(
    test_case: CursorAttributeTestCase,
) -> None:
    cursor: _Cursor = _Cursor()
    proxy: _SnowflakeCursor = _SnowflakeConnection(_RawConnection(cursor)).cursor()

    proxy.arraysize = test_case.arraysize

    assert cursor.arraysize == test_case.expected_arraysize


@pytest.mark.parametrize(
    "test_case",
    [
        QueryTagPolicyTestCase(
            description="caller tag is preserved while sfqid remains authoritative",
            caller_tag="caller-owned-tag",
            expected_calls=1,
            expected_query_id="01c-query-id",
            expected_status="success",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_caller_query_tag_when_executing_then_tag_is_preserved_and_sfqid_is_recorded(
    test_case: QueryTagPolicyTestCase,
    tmp_path: Path,
) -> None:
    cursor: _Cursor = _Cursor()
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    ledger_path: Path = tmp_path / "statements.jsonl"

    with CostContext.scope(
        run_id="caller-tag-run",
        resource_type="model",
        resource_name="orders",
        ledger_path=ledger_path,
    ):
        connection.execute("SELECT 1", statement_params={"QUERY_TAG": test_case.caller_tag})

    assert cursor.calls == test_case.expected_calls
    assert cursor.statement_params == {"QUERY_TAG": test_case.caller_tag}
    payload: dict[str, Any] = read_ledger(ledger_path)
    assert payload["query_id"] == test_case.expected_query_id
    assert payload["status"] == test_case.expected_status


@pytest.mark.parametrize(
    "test_case",
    [
        QueryTagPolicyTestCase(
            description="rejected caller tag is not stripped or retried",
            caller_tag="caller-owned-tag",
            expected_calls=1,
            expected_query_id=None,
            expected_status="failed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rejected_caller_query_tag_when_executing_then_tag_is_not_stripped_or_retried(
    test_case: QueryTagPolicyTestCase,
    tmp_path: Path,
) -> None:
    cursor: _QueryTagRejectingCursor = _QueryTagRejectingCursor()
    connection: _SnowflakeConnection = _SnowflakeConnection(_RawConnection(cursor))
    ledger_path: Path = tmp_path / "statements.jsonl"

    with pytest.raises(RuntimeError, match="unsupported statement parameter QUERY_TAG"):
        with CostContext.scope(
            run_id="caller-tag-run",
            resource_type="model",
            resource_name="orders",
            ledger_path=ledger_path,
        ):
            connection.execute("SELECT 1", statement_params={"QUERY_TAG": test_case.caller_tag})

    assert cursor.calls == test_case.expected_calls
    assert cursor.statement_params == {"QUERY_TAG": test_case.caller_tag}
    payload: dict[str, Any] = read_ledger(ledger_path)
    assert payload["query_id"] == test_case.expected_query_id
    assert payload["status"] == test_case.expected_status
