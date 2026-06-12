"""Runtime node result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class NodeResultRecord:
    """One persisted runtime result row."""

    node_type: str
    node_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    run_id: str
    status: str
    payload: object | None
    metadata: dict[str, object] = field(default_factory=dict)
    error_message: str | None = None
    materialized: bool | None = None
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class NodeResultEnvelope:
    """User-facing persisted runtime result envelope."""

    node_type: str
    node_name: str
    run_id: str
    status: str
    payload: object | None
    metadata: dict[str, object]
    error_message: str | None
    materialized: bool | None
    ts: datetime
