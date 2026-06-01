"""Test types for Rivers integration e2e tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiversSqlBuildE2ETestCase:
    """Test case for SQLBuild Rivers integration e2e verification."""

    description: str
    expected_success: bool
    expected_asset_names: frozenset[str]
    expected_table_names: tuple[str, ...]


@dataclass(frozen=True)
class RiversPlaygroundE2ETestCase:
    """Test case for generated Rivers playground execution."""

    description: str
    expected_success: bool
    expected_table_names: tuple[str, ...]
    expected_schema: str


@dataclass(frozen=True)
class RiversPythonNodesArtifactE2ETestCase:
    """Test case for real Python-node DAG artifacts consumed by Rivers."""

    description: str
    expected_asset_names: frozenset[str]
    expected_task_deps: tuple[str, ...]
    expected_asset_deps: tuple[str, ...]
    expected_task_group: str
    expected_asset_group: str
