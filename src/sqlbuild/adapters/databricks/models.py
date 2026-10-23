"""Databricks adapter models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UsageQuery:
    """One system.access.table_lineage read: its SQL and named parameters."""

    sql: str
    params: dict[str, object]
