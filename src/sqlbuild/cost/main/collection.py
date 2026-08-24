"""Snowflake cost collection entry point."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlbuild.cost._helpers.snowflake import collect_snowflake_run_cost
from sqlbuild.cost.models import RunCostSummary


def collect_snowflake_cost(
    *,
    connection: Any,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    statement_ledger_path: Path,
    usd_per_credit: Decimal,
    rate_source: str,
    attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> RunCostSummary:
    return collect_snowflake_run_cost(
        connection=connection,
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        statement_ledger_path=statement_ledger_path,
        usd_per_credit=usd_per_credit,
        rate_source=rate_source,
        attempts=attempts,
        retry_delay_seconds=retry_delay_seconds,
    )
