"""Snowflake cost collection over runs with tens of thousands of statements."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sqlbuild._native import collect_snowflake_cost
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.cost.models import RunCostSummary
from sqlbuild.cost.types import CostStatus
from tests.unit.src.sqlbuild.cost._test_types import (
    SnowflakeCostFailureMessageTestCase,
    SnowflakeLargeRunCostTestCase,
    SnowflakeScaleTestCase,
)
from tests.unit.src.sqlbuild.cost.helpers import history_row, run_history_rows, write_ledger

_ORIGIN: datetime = datetime(2026, 8, 23, 1, tzinfo=UTC)
_RUN_ID: str = "run-nightly"


_START_PATTERN: re.Pattern[str] = re.compile(
    r"END_TIME_RANGE_START => TO_TIMESTAMP_LTZ\('([^']+)'\)"
)
_END_PATTERN: re.Pattern[str] = re.compile(r"END_TIME_RANGE_END => TO_TIMESTAMP_LTZ\('([^']+)'\)")
_LIMIT_PATTERN: re.Pattern[str] = re.compile(r"RESULT_LIMIT => (\d+)")
STATEMENT_TIMEOUT_ERRNO: int = 630


class StatementTimeoutError(Exception):
    """The error a Snowflake read raises when it reaches its statement timeout."""

    def __init__(self, *, seconds: str) -> None:
        super().__init__(
            f"000630 (57014): Statement reached its statement or warehouse timeout of "
            f"{seconds} second(s) and was canceled."
        )
        self.errno: int = STATEMENT_TIMEOUT_ERRNO


@dataclass
class HistoryRead:
    """One query-history read: its window, SQL length and statement timeout."""

    start: datetime
    end: datetime | None
    sql_length: int
    timeout_seconds: str


class _Cursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows: list[tuple[Any, ...]] = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows


@dataclass
class _FakeQueryHistory:
    """Answers `INFORMATION_SCHEMA.QUERY_HISTORY` reads from fixed rows, like Snowflake does.

    Rows are filtered by end time, the open-ended read also returns running queries, and at most
    `RESULT_LIMIT` rows are returned. A read wider than `timeout_window` raises Snowflake's
    statement-timeout error, standing in for a read too slow for its statement timeout.
    """

    rows: list[tuple[Any, ...]]
    timeout_window: timedelta | None = None
    reads: list[HistoryRead] = field(default_factory=list)

    @property
    def widest_bounded_read(self) -> timedelta:
        """The widest end-time window of any bounded read."""

        return max(
            (read.end - read.start for read in self.reads if read.end is not None),
            default=timedelta(0),
        )

    @property
    def longest_sql(self) -> int:
        """The length of the longest SQL statement read."""

        return max(read.sql_length for read in self.reads)

    def execute(self, sql: str, **kwargs: Any) -> _Cursor:
        assert "INFORMATION_SCHEMA.QUERY_HISTORY" in sql
        start_match: re.Match[str] | None = _START_PATTERN.search(sql)
        limit_match: re.Match[str] | None = _LIMIT_PATTERN.search(sql)
        assert start_match is not None and limit_match is not None
        end_match: re.Match[str] | None = _END_PATTERN.search(sql)
        start: datetime = datetime.fromisoformat(start_match.group(1))
        end: datetime | None = (
            datetime.fromisoformat(end_match.group(1)) if end_match is not None else None
        )
        timeout_seconds: str = kwargs["statement_params"]["STATEMENT_TIMEOUT_IN_SECONDS"]
        self.reads.append(
            HistoryRead(start=start, end=end, sql_length=len(sql), timeout_seconds=timeout_seconds)
        )
        latest_end: datetime = end if end is not None else max(row[7] or start for row in self.rows)
        if self.timeout_window is not None and latest_end - start > self.timeout_window:
            raise StatementTimeoutError(seconds=timeout_seconds)
        matched: list[tuple[Any, ...]] = [
            row
            for row in self.rows
            if (row[7] is None and end is None)
            or (row[7] is not None and row[7] >= start and (end is None or row[7] < end))
        ]
        return _Cursor(matched[: int(limit_match.group(1))])


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeScaleTestCase(
            description="a 78-minute run of 20,000 statements is read in bounded slices",
            statement_count=20_000,
            duration_minutes=78,
            timeout_window=None,
            expected_status=CostStatus.COMPLETE,
            expected_query_count=20_000,
        ),
        SnowflakeScaleTestCase(
            description="slices that reach the statement timeout are split and retried",
            statement_count=6_500,
            duration_minutes=42,
            timeout_window=timedelta(minutes=8),
            expected_status=CostStatus.COMPLETE,
            expected_query_count=6_500,
        ),
        SnowflakeScaleTestCase(
            description="history that times out at every width is reported pending with its cause",
            statement_count=6_500,
            duration_minutes=42,
            timeout_window=timedelta(0),
            expected_status=CostStatus.PENDING,
            expected_query_count=0,
            expected_message_fragments=(
                "10-second statement timeout",
                f"Run `sqb cost {_RUN_ID}` to retry.",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_large_run_when_collecting_snowflake_cost_then_sql_stays_bounded(
    test_case: SnowflakeScaleTestCase,
    tmp_path: Path,
) -> None:
    duration: timedelta = timedelta(minutes=test_case.duration_minutes)
    rows: list[tuple[Any, ...]] = run_history_rows(
        origin=_ORIGIN, statement_count=test_case.statement_count, duration=duration
    )
    ledger_path: Path = tmp_path / "statements.jsonl"
    write_ledger(path=ledger_path, run_id=_RUN_ID, rows=rows)
    history: _FakeQueryHistory = _FakeQueryHistory(
        rows=rows, timeout_window=test_case.timeout_window
    )

    summary: RunCostSummary = collect_snowflake_cost(
        connection=history,
        run_id=_RUN_ID,
        started_at=_ORIGIN,
        completed_at=_ORIGIN + duration,
        statement_ledger_path=ledger_path,
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
        attempts=1,
    )

    assert summary.status == test_case.expected_status
    assert summary.query_count == test_case.expected_query_count
    assert summary.expected_statement_count == test_case.statement_count
    for fragment in test_case.expected_message_fragments:
        assert fragment in (summary.message or "")
    assert history.longest_sql < test_case.expected_max_sql_length
    assert {read.timeout_seconds for read in history.reads} == {"10"}
    assert history.widest_bounded_read <= test_case.expected_max_slice


class _ClosingHistory(_FakeQueryHistory):
    def close(self) -> None:
        return None


class ProgrammingError(Exception):
    """Stands in for the Snowflake connector's error of the same name."""


class _FailingHistory(_ClosingHistory):
    def execute(self, sql: str, **kwargs: Any) -> Any:
        del sql, kwargs
        raise ProgrammingError(
            "002003 (02000): SQL compilation error:\nDatabase 'ANALYTICS' does not exist."
        )


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeLargeRunCostTestCase(
            description="a large run's history is collected completely",
            timeout_window=None,
            expected_status=CostStatus.COMPLETE,
            expected_message_fragment="",
        ),
        SnowflakeLargeRunCostTestCase(
            description="history too slow to read leaves the run pending, naming the timeout",
            timeout_window=timedelta(0),
            expected_status=CostStatus.PENDING,
            expected_message_fragment="statement timeout",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_large_run_when_adapter_collects_cost_then_failures_stay_non_fatal(
    test_case: SnowflakeLargeRunCostTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    origin: datetime = datetime(2026, 8, 23, 1, tzinfo=UTC)
    rows: list[tuple[Any, ...]] = [
        history_row(query_id=f"q-{index:05d}", ended_at=origin + timedelta(seconds=index // 3))
        for index in range(12_000)
    ]
    ledger_path: Path = tmp_path / "statements.jsonl"
    write_ledger(path=ledger_path, run_id="run-large", rows=rows)
    history: _ClosingHistory = _ClosingHistory(rows=rows, timeout_window=test_case.timeout_window)
    monkeypatch.setattr(adapter, "connect", lambda config: history)

    summary: RunCostSummary = adapter.collect_run_cost(
        connection_config={},
        target_database="ANALYTICS",
        run_id="run-large",
        started_at=origin,
        completed_at=origin + timedelta(seconds=4_000),
        statement_ledger_path=ledger_path,
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
    )

    assert summary.status == test_case.expected_status
    assert test_case.expected_message_fragment in (summary.message or "")
    assert history.longest_sql < test_case.expected_max_sql_length


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeCostFailureMessageTestCase(
            description="a multi-line Snowflake error is named on one line",
            expected_status=CostStatus.COLLECTION_FAILED,
            expected_message=(
                "Snowflake cost collection failed (ProgrammingError: 002003 (02000): "
                "SQL compilation error: Database 'ANALYTICS' does not exist.)."
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_query_history_error_when_adapter_collects_cost_then_message_names_cause(
    test_case: SnowflakeCostFailureMessageTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    origin: datetime = datetime(2026, 8, 23, 1, tzinfo=UTC)
    rows: list[tuple[Any, ...]] = [history_row(query_id="q-1", ended_at=origin)]
    ledger_path: Path = tmp_path / "statements.jsonl"
    write_ledger(path=ledger_path, run_id="run-failed", rows=rows)
    monkeypatch.setattr(adapter, "connect", lambda config: _FailingHistory(rows=rows))

    summary: RunCostSummary = adapter.collect_run_cost(
        connection_config={},
        target_database="ANALYTICS",
        run_id="run-failed",
        started_at=origin,
        completed_at=origin + timedelta(seconds=1),
        statement_ledger_path=ledger_path,
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
    )

    assert summary.status == test_case.expected_status
    assert summary.message == test_case.expected_message
