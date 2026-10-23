"""Test types for build --no-tests --no-audits e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunE2ETestCase:
    """Test case for sqb build --no-tests --no-audits e2e verification."""

    description: str
    expected_exit_code: int
    expected_table_names: tuple[str, ...]
    expected_view_names: tuple[str, ...]
    expected_fact_orders_data: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    expected_output_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class PythonNodeRunTestCase:
    """One Python-node project built with ``--no-tests --no-audits`` and its observable order.

    ``expected_order`` pairs name what must appear earlier, then later, in the execution section.
    """

    description: str
    project_name: str
    files: dict[str, str]
    select: str
    expected_order: tuple[tuple[str, str], ...] = ()
    expected_output_fragments: tuple[str, ...] = ()
    expected_markers: dict[str, str] = field(default_factory=dict)
    expected_table_names: tuple[str, ...] = ()
    expected_row_counts: dict[str, int] = field(default_factory=dict)
