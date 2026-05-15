"""Test types for Dagster integration e2e tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DagsterSqlBuildE2ETestCase:
    """Test case for SQLBuild Dagster integration e2e verification."""

    description: str
    expected_success: bool
    expected_dag_artifact: str
    expected_table_names: tuple[str, ...]
    expected_asset_keys: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class DagsterSqlBuildSelectionE2ETestCase:
    """Test case for Dagster subset selection passed to SQLBuild."""

    description: str
    selected_asset_keys: tuple[tuple[str, ...], ...]
    expected_success: bool
    expected_selector_file_contents: str
    expected_selector_log_line: str
    expected_table_names: tuple[str, ...]
