"""Persisted run-cost domain models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlbuild.cost.types import CostStatus


@dataclass(frozen=True)
class QueryCostObservation:
    query_id: str
    warehouse_name: str
    warehouse_size: str
    warehouse_type: str | None
    cluster_number: int | None
    started_at: datetime
    completed_at: datetime
    execution_ms: int
    bytes_scanned: int
    execution_status: str
    run_id: str | None = None
    resource_type: str | None = None
    resource_name: str | None = None


@dataclass(frozen=True)
class StatementExecutionTelemetry:
    """Completed Snowflake statement identity and local elapsed time."""

    query_id: str | None
    status: str
    elapsed_seconds: float
    resource_type: str
    resource_name: str
    phase: str


@dataclass(frozen=True)
class CostResourceContext:
    run_id: str
    resource_type: str
    resource_name: str
    ledger_path: Path | None = None
    phase: str = "execute"
    attempt: int = 1
    on_statement_complete: Callable[[StatementExecutionTelemetry], None] | None = None


@dataclass(frozen=True)
class ResourceCost:
    resource_type: str
    resource_name: str
    warehouse_name: str
    warehouse_size: str
    warehouse_type: str | None
    cluster_number: int | None
    query_count: int
    attributed_seconds: Decimal
    bytes_scanned: int
    estimated_compute_credits: Decimal
    estimated_usd: Decimal


@dataclass(frozen=True)
class RunCostSummary:
    status: CostStatus
    usd_per_credit: Decimal
    rate_source: str
    resources: tuple[ResourceCost, ...] = ()
    query_count: int = 0
    attributed_seconds: Decimal = Decimal(0)
    bytes_scanned: int = 0
    estimated_compute_credits: Decimal = Decimal(0)
    estimated_usd: Decimal = Decimal(0)
    expected_statement_count: int = 0
    observed_statement_count: int = 0
    missing_statement_count: int = 0
    skipped_statement_count: int = 0
    source: str = "snowflake_information_schema_query_history"
    method: str = "equal_share_visible_query_busy_time_v1"
    limitations: tuple[str, ...] = ()
    message: str | None = None


@dataclass(frozen=True)
class CostRunRecord:
    run_id: str
    adapter_name: str
    target_name: str | None
    build_status: str
    started_at: datetime
    completed_at: datetime
    cost: RunCostSummary
    version: int = 1
    had_executable_work: bool | None = None


@dataclass(frozen=True)
class StatementLedgerEntry:
    statement_id: str
    run_id: str
    resource_type: str
    resource_name: str
    phase: str
    attempt: int
    query_id: str | None
    status: str
    started_at: datetime
    completed_at: datetime
