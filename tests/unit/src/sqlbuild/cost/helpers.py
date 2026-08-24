from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlbuild.cost.models import CostRunRecord, QueryCostObservation, ResourceCost, RunCostSummary
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
