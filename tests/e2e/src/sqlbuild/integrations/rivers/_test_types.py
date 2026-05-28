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
