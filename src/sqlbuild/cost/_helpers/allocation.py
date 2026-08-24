"""Concurrency-safe Snowflake busy-compute attribution."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from sqlbuild.cost.constants import STANDARD_WAREHOUSE_TYPE
from sqlbuild.cost.models import QueryCostObservation, ResourceCost, RunCostSummary
from sqlbuild.cost.types import CostStatus

_CREDITS_PER_HOUR: dict[str, Decimal] = {
    "X-SMALL": Decimal(1),
    "SMALL": Decimal(2),
    "MEDIUM": Decimal(4),
    "LARGE": Decimal(8),
    "X-LARGE": Decimal(16),
    "2X-LARGE": Decimal(32),
    "3X-LARGE": Decimal(64),
    "4X-LARGE": Decimal(128),
    "5X-LARGE": Decimal(256),
    "6X-LARGE": Decimal(512),
}


def allocate_run_cost(
    *,
    observations: tuple[QueryCostObservation, ...],
    run_id: str,
    usd_per_credit: Decimal,
    rate_source: str,
    result_limit_reached: bool = False,
) -> RunCostSummary:
    run_queries: tuple[QueryCostObservation, ...] = tuple(
        observation for observation in observations if observation.run_id == run_id
    )
    if not run_queries:
        return RunCostSummary(
            status=CostStatus.PENDING,
            usd_per_credit=usd_per_credit,
            rate_source=rate_source,
            message="Snowflake query history is not complete yet.",
        )

    attributed: dict[str, Decimal] = defaultdict(Decimal)
    by_warehouse: dict[tuple[str, str, str | None, int | None], list[QueryCostObservation]] = (
        defaultdict(list)
    )
    for observation in observations:
        by_warehouse[
            (
                observation.warehouse_name,
                observation.warehouse_size,
                observation.warehouse_type,
                observation.cluster_number,
            )
        ].append(observation)

    for warehouse_queries in by_warehouse.values():
        boundaries: list[datetime] = _query_boundaries(queries=warehouse_queries)
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            if end <= start:
                continue
            active: tuple[QueryCostObservation, ...] = tuple(
                query
                for query in warehouse_queries
                if query.started_at < end and query.completed_at > start
            )
            if not active:
                continue
            seconds: Decimal = Decimal(str((end - start).total_seconds())) / Decimal(len(active))
            for query in active:
                if query.run_id == run_id:
                    attributed[query.query_id] += seconds

    grouped: dict[tuple[str, str, str, str, str | None, int | None], list[QueryCostObservation]] = (
        defaultdict(list)
    )
    for query in run_queries:
        grouped[
            (
                query.resource_type or "unknown",
                query.resource_name or "unknown",
                query.warehouse_name,
                query.warehouse_size,
                query.warehouse_type,
                query.cluster_number,
            )
        ].append(query)

    limitations: list[str] = []
    resources: list[ResourceCost] = []
    for (
        resource_type,
        resource_name,
        warehouse_name,
        warehouse_size,
        warehouse_type,
        cluster_number,
    ), queries in grouped.items():
        rate: Decimal | None = _CREDITS_PER_HOUR.get(warehouse_size.upper())
        if warehouse_type is None:
            limitations.append(f"Unknown warehouse type for {warehouse_name}")
        elif warehouse_type.upper() != STANDARD_WAREHOUSE_TYPE:
            limitations.append(f"Unsupported Snowflake warehouse type: {warehouse_type}")
            continue
        if cluster_number is None:
            limitations.append(f"Unknown cluster number for {warehouse_name}")
        if rate is None:
            limitations.append(f"Unknown Snowflake warehouse size: {warehouse_size}")
            continue
        seconds = sum((attributed[query.query_id] for query in queries), Decimal(0))
        credits: Decimal = seconds * rate / Decimal(3600)
        resources.append(
            ResourceCost(
                resource_type=resource_type,
                resource_name=resource_name,
                warehouse_name=warehouse_name,
                warehouse_size=warehouse_size,
                warehouse_type=warehouse_type,
                cluster_number=cluster_number,
                query_count=len(queries),
                attributed_seconds=seconds,
                bytes_scanned=sum(query.bytes_scanned for query in queries),
                estimated_compute_credits=credits,
                estimated_usd=credits * usd_per_credit,
            )
        )
    if result_limit_reached:
        limitations.append("Snowflake query-history result limit was reached.")
    resources.sort(
        key=lambda item: (
            -item.estimated_usd,
            item.resource_name,
            item.resource_type,
            item.warehouse_name,
            item.warehouse_size,
            item.warehouse_type or "",
            -1 if item.cluster_number is None else item.cluster_number,
        )
    )
    return RunCostSummary(
        status=CostStatus.PARTIAL if limitations else CostStatus.COMPLETE,
        usd_per_credit=usd_per_credit,
        rate_source=rate_source,
        resources=tuple(resources),
        query_count=len(run_queries),
        attributed_seconds=sum((item.attributed_seconds for item in resources), Decimal(0)),
        bytes_scanned=sum(item.bytes_scanned for item in resources),
        estimated_compute_credits=sum(
            (item.estimated_compute_credits for item in resources), Decimal(0)
        ),
        estimated_usd=sum((item.estimated_usd for item in resources), Decimal(0)),
        limitations=tuple(sorted(set(limitations))),
    )


def _query_boundaries(*, queries: list[QueryCostObservation]) -> list[datetime]:
    boundaries: set[datetime] = set()
    for query in queries:
        boundaries.add(query.started_at)
        boundaries.add(query.completed_at)
    return sorted(boundaries)
