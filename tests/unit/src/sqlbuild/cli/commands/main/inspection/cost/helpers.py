from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlbuild.cli.commands.models import CostCommandRequest
from sqlbuild.cost.models import CostRunRecord, ResourceCost, RunCostSummary
from sqlbuild.cost.types import CostStatus


def build_cost_request(
    *, project_dir: Path, selector: str = "latest", **overrides: object
) -> CostCommandRequest:
    values: dict[str, object] = {
        "project_dir": project_dir,
        "selector": selector,
        "no_color": True,
        "limit": None,
        "no_limit": False,
        "sort": None,
        "order": None,
        "since": None,
        "until": None,
        "json_output": False,
        "json_output_path": None,
    }
    values.update(overrides)
    return CostCommandRequest(**values)  # type: ignore[arg-type]


def build_cost_run_record(*, run_id: str, completed_at: datetime, usd: str) -> CostRunRecord:
    return CostRunRecord(
        run_id=run_id,
        adapter_name="snowflake",
        target_name="dev",
        build_status="success",
        started_at=completed_at - timedelta(seconds=1),
        completed_at=completed_at,
        cost=RunCostSummary(
            status=CostStatus.COMPLETE,
            usd_per_credit=Decimal("3.00"),
            rate_source="default",
            resources=(
                ResourceCost(
                    resource_type="model",
                    resource_name="orders",
                    warehouse_name="DEV_WH",
                    warehouse_size="X-Small",
                    warehouse_type="STANDARD",
                    cluster_number=1,
                    query_count=1,
                    attributed_seconds=Decimal(1),
                    bytes_scanned=10,
                    estimated_compute_credits=Decimal(usd) / Decimal("3.00"),
                    estimated_usd=Decimal(usd),
                ),
            ),
            estimated_compute_credits=Decimal(usd) / Decimal("3.00"),
            estimated_usd=Decimal(usd),
        ),
    )
