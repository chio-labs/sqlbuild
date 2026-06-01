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
    expected_json_metadata_asset_key: tuple[str, ...]
    expected_json_metadata_keys: tuple[str, ...]
    expected_check_asset_key: tuple[str, ...]
    expected_check_names: tuple[str, ...]
    expected_warn_check_name: str


@dataclass(frozen=True)
class DagsterSqlBuildSelectionE2ETestCase:
    """Test case for Dagster subset selection passed to SQLBuild."""

    description: str
    selected_asset_keys: tuple[tuple[str, ...], ...]
    expected_success: bool
    expected_selector_file_contents: str
    expected_selector_log_line: str
    expected_table_names: tuple[str, ...]


@dataclass(frozen=True)
class DagsterSqlBuildFailedCheckE2ETestCase:
    """Test case for failed SQLBuild checks emitted through Dagster."""

    description: str
    selected_asset_key: tuple[str, ...]
    expected_check_names: tuple[str, ...]


@dataclass(frozen=True)
class DagsterSqlBuildScenarioE2ETestCase:
    """Test case for SQLBuild scenario checks emitted through Dagster."""

    description: str
    selected_asset_keys: tuple[tuple[str, ...], ...]
    expected_command_fragment: str
    unexpected_command_fragment: str
    daily_revenue_asset_key: tuple[str, ...]
    expected_daily_revenue_check_names: tuple[str, ...]
    scenario_order_prices_asset_key: tuple[str, ...]
    unexpected_scenario_order_prices_check_names: tuple[str, ...]


@dataclass(frozen=True)
class DagsterSqlBuildStreamingE2ETestCase:
    """Test case for live SQLBuild stream forwarding through Dagster."""

    description: str
    selected_asset_key: tuple[str, ...]
    expected_stdout_fragment: str


@dataclass(frozen=True)
class DagsterSqlBuildLoaderE2ETestCase:
    """Test case for SQLBuild source loaders through Dagster assets."""

    description: str
    selected_asset_key: tuple[str, ...]
    expected_success: bool
    expected_selector_file_contents: str
    expected_table_names: tuple[str, ...]
    expected_metadata_asset_key: tuple[str, ...]
    expected_metadata_keys: tuple[str, ...]


@dataclass(frozen=True)
class DagsterPlaygroundE2ETestCase:
    """Test case for generated Dagster playground execution."""

    description: str
    expected_success: bool
    expected_table_names: tuple[str, ...]
    expected_schema: str


@dataclass(frozen=True)
class DagsterPythonNodesArtifactE2ETestCase:
    """Test case for real Python-node DAG artifacts consumed by Dagster."""

    description: str
    expected_asset_keys: tuple[tuple[str, ...], ...]
    expected_check_names: tuple[str, ...]
    expected_task_group: str
    expected_asset_group: str
