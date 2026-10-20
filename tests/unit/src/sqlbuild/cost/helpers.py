import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlbuild._native import CostRunRecord, QueryCostObservation, ResourceCost
from sqlbuild.cost.models import RunCostSummary
from sqlbuild.cost.types import CostStatus


def build_query_cost_observation(
    *,
    query_id: str,
    start_seconds: int,
    end_seconds: int,
    run_id: str | None,
    resource_type: str | None,
    resource_name: str | None,
    warehouse_size: str = "X-Small",
) -> QueryCostObservation:
    origin: datetime = datetime(2026, 8, 23, tzinfo=UTC)
    return QueryCostObservation(
        query_id=query_id,
        warehouse_name="DEV_WH",
        warehouse_size=warehouse_size,
        warehouse_type="STANDARD",
        cluster_number=1,
        started_at=origin + timedelta(seconds=start_seconds),
        completed_at=origin + timedelta(seconds=end_seconds),
        execution_ms=(end_seconds - start_seconds) * 1000,
        bytes_scanned=100,
        execution_status="SUCCESS",
        run_id=run_id,
        resource_type=resource_type,
        resource_name=resource_name,
    )


def build_cost_run_record(*, run_id: str, completed_at: datetime) -> CostRunRecord:
    resource: ResourceCost = ResourceCost(
        resource_type="model",
        resource_name="orders",
        warehouse_name="DEV_WH",
        warehouse_size="X-Small",
        warehouse_type="STANDARD",
        cluster_number=1,
        query_count=1,
        attributed_seconds=Decimal("1.25"),
        bytes_scanned=1024,
        estimated_compute_credits=Decimal("0.0003472222222222222222222222222"),
        estimated_usd=Decimal("0.001041666666666666666666666667"),
    )
    return CostRunRecord(
        run_id=run_id,
        adapter_name="snowflake",
        target_name="dev",
        build_status="success",
        started_at=completed_at - timedelta(seconds=2),
        completed_at=completed_at,
        cost=RunCostSummary(
            status=CostStatus.COMPLETE,
            usd_per_credit=Decimal("3.00"),
            rate_source="default",
            resources=(resource,),
            query_count=1,
            attributed_seconds=resource.attributed_seconds,
            bytes_scanned=resource.bytes_scanned,
            estimated_compute_credits=resource.estimated_compute_credits,
            estimated_usd=resource.estimated_usd,
        ),
    )


def history_row(*, query_id: str, ended_at: datetime) -> tuple[Any, ...]:
    """One successful one-second warehouse query ending at `ended_at`."""

    return (
        query_id,
        "",
        "TRANSFORM_WH",
        "X-Small",
        "STANDARD",
        1,
        ended_at - timedelta(seconds=1),
        ended_at,
        1000,
        100,
        "SUCCESS",
        "INSERT",
        None,
        ended_at,
    )


def run_history_rows(
    *, origin: datetime, statement_count: int, duration: timedelta
) -> list[tuple[Any, ...]]:
    """History rows of one run whose statements end evenly across `duration`."""

    step: timedelta = duration / statement_count
    return [
        history_row(query_id=f"q-{index:05d}", ended_at=origin + step * (index + 1))
        for index in range(statement_count)
    ]


def write_ledger(*, path: Path, run_id: str, rows: list[tuple[Any, ...]]) -> None:
    """Write one statement-ledger entry for each history row."""

    with path.open("w", encoding="utf-8") as ledger:
        for index, row in enumerate(rows):
            ledger.write(
                json.dumps(
                    {
                        "statement_id": f"statement-{index}",
                        "run_id": run_id,
                        "resource_type": "model",
                        "resource_name": f"orders_{index % 1400}",
                        "phase": "execute",
                        "attempt": 1,
                        "query_id": row[0],
                        "status": "success",
                        "started_at": row[6].isoformat(),
                        "completed_at": row[7].isoformat(),
                    }
                )
                + "\n"
            )
