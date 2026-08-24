from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.main.collection import collect_snowflake_cost
from sqlbuild.cost.models import RunCostSummary
from sqlbuild.cost.types import CostStatus
from tests.integration.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeCostTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeCostTestCase(
            description="tagged statement is attributed from real query history",
            expected_statuses=frozenset({CostStatus.COMPLETE, CostStatus.PARTIAL}),
            expected_query_count=1,
            expected_resource_name="cost_probe",
            expected_minimum_credits=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_tagged_statement_when_collecting_real_history_then_exact_query_is_attributed(
    test_case: SnowflakeCostTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    tmp_path: Path,
) -> None:
    run_id = "snowflake-cost-integration"
    ledger_path: Path = tmp_path / "statements.jsonl"
    started_at: datetime = datetime.now(UTC)
    with CostContext.scope(
        run_id=run_id,
        resource_type="model",
        resource_name="cost_probe",
        ledger_path=ledger_path,
    ):
        cursor: Any = adapter.execute(
            connection=connection,
            sql="SELECT COUNT(*) FROM TABLE(GENERATOR(ROWCOUNT => 1000000))",
        )
        assert cursor.fetchone()[0] == 1_000_000
    completed_at: datetime = datetime.now(UTC)

    summary: RunCostSummary = collect_snowflake_cost(
        connection=connection,
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        statement_ledger_path=ledger_path,
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
        attempts=10,
        retry_delay_seconds=0.5,
    )

    assert summary.status in test_case.expected_statuses
    assert summary.query_count == test_case.expected_query_count
    assert summary.resources[0].resource_name == test_case.expected_resource_name
    assert summary.estimated_compute_credits >= test_case.expected_minimum_credits
