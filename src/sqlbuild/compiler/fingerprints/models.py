"""Fingerprint domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Fingerprint:
    """One applied fingerprint record from a successful materialization."""

    model_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    run_id: str
    query_hash: str
    ast_hash: str | None
    schema_fingerprint: str
    query_sql: str
    ts: datetime
    metadata_json: str = "{}"


@dataclass(frozen=True)
class FingerprintSet:
    """Latest fingerprints per model for one target schema."""

    schema: str
    fingerprints: dict[str, Fingerprint]
