"""Cost observability type declarations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlbuild.cost.models import RunCostSummary


class CostCapability(StrEnum):
    NONE = "none"
    SNOWFLAKE_QUERY_HISTORY = "snowflake_query_history"


class CostStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"
    COLLECTION_FAILED = "collection_failed"


@runtime_checkable
class CostAwareAdapter(Protocol):
    """Adapter extension implemented only by warehouses with cost telemetry."""

    def cost_capability(self) -> CostCapability: ...

    def collect_run_cost(
        self,
        *,
        connection_config: dict[str, object],
        target_database: str | None,
        run_id: str,
        started_at: datetime,
        completed_at: datetime,
        statement_ledger_path: Path,
        usd_per_credit: Decimal,
        rate_source: str,
    ) -> RunCostSummary: ...
