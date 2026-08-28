from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cost._helpers.snowflake import (
    _parse_sqlbuild_tag,
    _render_open_query_history_sql,
    _render_query_history_sql,
)
from sqlbuild.cost.constants import COST_TELEMETRY_HEALTH
from sqlbuild.cost.main.collection import collect_snowflake_cost
from sqlbuild.cost.models import RunCostSummary
from sqlbuild.cost.types import CostStatus
from tests.unit.src.sqlbuild.cost._test_types import (
    CollectSnowflakeCostTestCase,
    ParseQueryTagTestCase,
    RenderQueryHistorySqlTestCase,
    SnowflakeObservationTestCase,
)


class _Cursor:
    def __init__(self, rows: tuple[tuple[Any, ...], ...]) -> None:
        self.rows = rows

    def fetchall(self) -> tuple[tuple[Any, ...], ...]:
        return self.rows


class _Connection:
    def __init__(self, rows: tuple[tuple[Any, ...], ...]) -> None:
        self.rows = rows

    def execute(self, sql: str, **kwargs: Any) -> _Cursor:
        del kwargs
        assert "INFORMATION_SCHEMA.QUERY_HISTORY" in sql
        return _Cursor(self.rows)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderQueryHistorySqlTestCase(
            description="bounded query history uses valid table function",
            expected_fragments=(
                "TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(",
                "END_TIME_RANGE_START => TO_TIMESTAMP_LTZ('2026-08-23T10:00:00+00:00')",
                "END_TIME_RANGE_END => TO_TIMESTAMP_LTZ('2026-08-23T10:05:00+00:00')",
                "RESULT_LIMIT => 10000",
                "EXECUTION_STATUS",
            ),
            expected_excluded_fragment="WHERE EXECUTION_STATUS = 'SUCCESS'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_time_range_when_rendering_query_history_then_uses_valid_bounded_table_function(
    test_case: RenderQueryHistorySqlTestCase,
) -> None:
    sql: str = _render_query_history_sql(
        started_at=datetime(2026, 8, 23, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 23, 10, 5, tzinfo=UTC),
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql
    assert test_case.expected_excluded_fragment not in sql


@pytest.mark.parametrize(
    "test_case",
    [
        RenderQueryHistorySqlTestCase(
            description="open query history includes visible running queries",
            expected_fragments=(
                "TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(",
                "END_TIME_RANGE_START => TO_TIMESTAMP_LTZ('2026-08-23T10:00:00+00:00')",
                "RESULT_LIMIT => 10000",
                "EXECUTION_STATUS",
            ),
            expected_excluded_fragment="END_TIME_RANGE_END",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_start_time_when_rendering_open_history_then_running_queries_are_requested(
    test_case: RenderQueryHistorySqlTestCase,
) -> None:
    sql: str = _render_open_query_history_sql(started_at=datetime(2026, 8, 23, 10, 0, tzinfo=UTC))

    for fragment in test_case.expected_fragments:
        assert fragment in sql
    assert test_case.expected_excluded_fragment not in sql


@pytest.mark.parametrize(
    "test_case",
    [
        ParseQueryTagTestCase(
            description="sqlbuild query tag returns context",
            query_tag=json.dumps(
                {
                    "app": "sqlbuild",
                    "v": 1,
                    "run_id": "run-1",
                    "resource_type": "model",
                    "resource_name": "orders",
                }
            ),
            expected_payload={
                "app": "sqlbuild",
                "v": 1,
                "run_id": "run-1",
                "resource_type": "model",
                "resource_name": "orders",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_query_tag_when_parsing_then_context_is_returned(
    test_case: ParseQueryTagTestCase,
) -> None:
    parsed: dict[str, Any] | None = _parse_sqlbuild_tag(test_case.query_tag)

    assert parsed == test_case.expected_payload


@pytest.mark.parametrize(
    "test_case",
    [
        ParseQueryTagTestCase(
            description="invalid JSON query tag returns none",
            query_tag="not-json",
            expected_payload=None,
        ),
        ParseQueryTagTestCase(
            description="unrelated query tag returns none",
            query_tag='{"app":"other","v":1}',
            expected_payload=None,
        ),
        ParseQueryTagTestCase(
            description="missing query tag returns none",
            query_tag=None,
            expected_payload=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unrelated_or_invalid_query_tag_when_parsing_then_none_is_returned(
    test_case: ParseQueryTagTestCase,
) -> None:
    assert _parse_sqlbuild_tag(test_case.query_tag) == test_case.expected_payload


@pytest.mark.parametrize(
    "test_case",
    [
        CollectSnowflakeCostTestCase(
            description="failed ledger query ID overrides forged query tag",
            expected_status=CostStatus.COMPLETE,
            expected_query_count=1,
            expected_resource_name="orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failed_ledger_query_and_forged_tag_when_collecting_then_exact_id_is_authoritative(
    test_case: CollectSnowflakeCostTestCase,
    tmp_path: Path,
) -> None:
    origin: datetime = datetime(2026, 8, 23, 10, tzinfo=UTC)
    tag: str = json.dumps(
        {
            "app": "sqlbuild",
            "v": 1,
            "run_id": "run-1",
            "resource_type": "model",
            "resource_name": "forged",
        }
    )
    rows: tuple[tuple[Any, ...], ...] = (
        (
            "q-run",
            "",
            "DEV_WH",
            "X-Small",
            "STANDARD",
            1,
            origin,
            origin + timedelta(seconds=2),
            2000,
            100,
            "FAIL_WITH_ERROR",
        ),
        (
            "q-forged",
            tag,
            "DEV_WH",
            "X-Small",
            "STANDARD",
            1,
            origin,
            origin + timedelta(seconds=2),
            2000,
            100,
            "SUCCESS",
        ),
    )
    ledger_path: Path = tmp_path / "statements.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "statement_id": "statement-1",
                "run_id": "run-1",
                "resource_type": "model",
                "resource_name": "orders",
                "phase": "execute",
                "attempt": 1,
                "query_id": "q-run",
                "status": "failed",
                "started_at": origin.isoformat(),
                "completed_at": (origin + timedelta(seconds=2)).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary: RunCostSummary = collect_snowflake_cost(
        connection=_Connection(rows),
        run_id="run-1",
        started_at=origin,
        completed_at=origin + timedelta(seconds=2),
        statement_ledger_path=ledger_path,
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
        attempts=1,
    )

    assert summary.status == test_case.expected_status
    assert summary.query_count == test_case.expected_query_count
    assert summary.resources[0].resource_name == test_case.expected_resource_name
    assert summary.resources[0].estimated_compute_credits == Decimal(1) / Decimal(3600)


@pytest.mark.parametrize(
    "test_case",
    [
        CollectSnowflakeCostTestCase(
            description="ledger persistence failure prevents false complete zero",
            expected_status=CostStatus.PARTIAL,
            expected_query_count=0,
            expected_resource_name="",
            expected_limitation_fragment="Statement-ledger persistence failed (OSError)",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_ledger_persistence_failure_when_collecting_then_summary_is_partial(
    test_case: CollectSnowflakeCostTestCase,
    tmp_path: Path,
) -> None:
    origin: datetime = datetime(2026, 8, 23, 10, tzinfo=UTC)
    COST_TELEMETRY_HEALTH.mark_ledger_failure(
        run_id="ledger-failure-run", error=OSError("disk unavailable")
    )

    summary: RunCostSummary = collect_snowflake_cost(
        connection=_Connection(()),
        run_id="ledger-failure-run",
        started_at=origin,
        completed_at=origin,
        statement_ledger_path=tmp_path / "statements.jsonl",
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
        attempts=1,
    )

    assert summary.status == test_case.expected_status
    assert summary.query_count == test_case.expected_query_count
    assert test_case.expected_resource_name == ""
    assert any(
        test_case.expected_limitation_fragment in limitation for limitation in summary.limitations
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeObservationTestCase(
            description="missing warehouse size is explicit partial coverage",
            warehouse_size=None,
            execution_ms=1000,
            execution_status="SUCCESS",
            expected_status=CostStatus.PARTIAL,
            expected_query_count=0,
            expected_limitation_fragment="missing Snowflake warehouse metadata",
        ),
        SnowflakeObservationTestCase(
            description="zero-compute statement is a complete observed zero",
            warehouse_size="X-Small",
            execution_ms=0,
            execution_status="SUCCESS",
            expected_status=CostStatus.COMPLETE,
            expected_query_count=0,
        ),
        SnowflakeObservationTestCase(
            description="cancelled cost-bearing statement remains attributable",
            warehouse_size="X-Small",
            execution_ms=1000,
            execution_status="CANCELED",
            expected_status=CostStatus.COMPLETE,
            expected_query_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_special_history_row_when_collecting_then_coverage_is_explicit(
    test_case: SnowflakeObservationTestCase,
    tmp_path: Path,
) -> None:
    origin: datetime = datetime(2026, 8, 23, 10, tzinfo=UTC)
    ledger_path: Path = tmp_path / "statements.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "statement_id": "statement-special",
                "run_id": "run-special",
                "resource_type": "model",
                "resource_name": "orders",
                "phase": "execute",
                "attempt": 1,
                "query_id": "q-special",
                "status": "success",
                "started_at": origin.isoformat(),
                "completed_at": (origin + timedelta(seconds=1)).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows: tuple[tuple[Any, ...], ...] = (
        (
            "q-special",
            "",
            "DEV_WH",
            test_case.warehouse_size,
            "STANDARD",
            1,
            origin,
            origin + timedelta(seconds=1),
            test_case.execution_ms,
            100,
            test_case.execution_status,
        ),
    )

    summary: RunCostSummary = collect_snowflake_cost(
        connection=_Connection(rows),
        run_id="run-special",
        started_at=origin,
        completed_at=origin + timedelta(seconds=1),
        statement_ledger_path=ledger_path,
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
        attempts=1,
    )

    assert summary.status == test_case.expected_status
    assert summary.query_count == test_case.expected_query_count
    assert summary.expected_statement_count == 1
    assert summary.observed_statement_count == 1
    assert summary.skipped_statement_count == (1 - test_case.expected_query_count)
    assert test_case.expected_limitation_fragment in " ".join(summary.limitations)


@pytest.mark.parametrize(
    "test_case",
    [
        CollectSnowflakeCostTestCase(
            description="visible running competitor shares overlapping warehouse busy time",
            expected_status=CostStatus.COMPLETE,
            expected_query_count=1,
            expected_resource_name="orders",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_visible_running_competitor_when_collecting_then_busy_time_is_shared(
    test_case: CollectSnowflakeCostTestCase,
    tmp_path: Path,
) -> None:
    origin: datetime = datetime(2026, 8, 23, 10, tzinfo=UTC)
    ledger_path: Path = tmp_path / "statements.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "statement_id": "statement-run",
                "run_id": "run-shared",
                "resource_type": "model",
                "resource_name": test_case.expected_resource_name,
                "phase": "execute",
                "attempt": 1,
                "query_id": "q-run",
                "status": "success",
                "started_at": origin.isoformat(),
                "completed_at": (origin + timedelta(seconds=1)).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows: tuple[tuple[Any, ...], ...] = (
        (
            "q-run",
            "",
            "DEV_WH",
            "X-Small",
            "STANDARD",
            1,
            origin,
            origin + timedelta(seconds=1),
            1000,
            100,
            "SUCCESS",
        ),
        (
            "q-running-competitor",
            "",
            "DEV_WH",
            "X-Small",
            "STANDARD",
            1,
            origin,
            None,
            1000,
            0,
            "RUNNING",
        ),
    )

    summary: RunCostSummary = collect_snowflake_cost(
        connection=_Connection(rows),
        run_id="run-shared",
        started_at=origin,
        completed_at=origin + timedelta(seconds=1),
        statement_ledger_path=ledger_path,
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
        attempts=1,
    )

    assert summary.status == test_case.expected_status
    assert summary.query_count == test_case.expected_query_count
    assert summary.resources[0].resource_name == test_case.expected_resource_name
    assert summary.resources[0].attributed_seconds == Decimal("0.5")


@pytest.mark.parametrize(
    "test_case",
    [
        CollectSnowflakeCostTestCase(
            description="aged out missing history becomes unavailable",
            expected_status=CostStatus.UNAVAILABLE,
            expected_query_count=0,
            expected_resource_name="",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_run_older_than_retention_when_history_is_missing_then_status_is_unavailable(
    test_case: CollectSnowflakeCostTestCase,
    tmp_path: Path,
) -> None:
    completed_at: datetime = datetime.now(UTC) - timedelta(days=8)
    started_at: datetime = completed_at - timedelta(seconds=1)
    ledger_path: Path = tmp_path / "statements.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "statement_id": "statement-expired",
                "run_id": "run-expired",
                "resource_type": "model",
                "resource_name": "orders",
                "phase": "execute",
                "attempt": 1,
                "query_id": "q-expired",
                "status": "success",
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary: RunCostSummary = collect_snowflake_cost(
        connection=_Connection(()),
        run_id="run-expired",
        started_at=started_at,
        completed_at=completed_at,
        statement_ledger_path=ledger_path,
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
        attempts=1,
    )

    assert summary.status == test_case.expected_status
    assert summary.query_count == test_case.expected_query_count
    assert "no longer available" in (summary.message or "")
