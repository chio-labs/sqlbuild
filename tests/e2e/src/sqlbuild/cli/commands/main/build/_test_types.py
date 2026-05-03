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


@dataclass(frozen=True)
class ModelBackedCursorBuildE2ETestCase:
    """Test case for model-backed cursor build e2e regression coverage."""

    description: str
    repo_files: dict[str, str]
    command: tuple[str, ...]
    expected_exit_code: int
    expected_table_names: tuple[str, ...]
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]
    expected_absent_runtime_fragments: tuple[str, ...] = field(default_factory=tuple)
