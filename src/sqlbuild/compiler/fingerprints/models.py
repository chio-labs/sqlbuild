"""Fingerprint domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Fingerprint:
    """One applied fingerprint record from a successful materialization."""

    node_type: str
    node_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    run_id: str
    definition_hash: str
    schema_fingerprint: str
    definition: str
    ts: datetime
    metadata_json: str = "{}"
    version_hash: str = ""


@dataclass(frozen=True)
class FingerprintSet:
    """Latest fingerprints per node name for one target schema."""

    schema: str
    fingerprints: dict[str, Fingerprint]
