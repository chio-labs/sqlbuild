"""Snowflake adapter models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UsageQuery:
    """One access-history read: its SQL and bound parameters."""

    sql: str
    params: tuple[object, ...]
