"""Test types for build e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BuildE2ETestCase:
    """Test case for sqb build e2e verification."""

    description: str
    expected_exit_code: int
    expected_table_names: tuple[str, ...]
    expected_view_names: tuple[str, ...]
    expected_seed_names: tuple[str, ...]
    expected_fact_orders_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_dim_customers_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_waffle_types_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_daily_revenue_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_daily_order_partitioned_data: tuple[tuple[object, ...], ...] = field(
        default_factory=tuple
    )
