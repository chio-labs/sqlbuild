"""Auditing identity models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditIdentity:
    """Stable identity values for one planned audit binding."""

    binding_key: str
    audit_name: str
    definition_fingerprint: str
    execution_fingerprint: str
    severity: str
    run_scope_phase: str
    attachment_kind: str
    attached_target_name: str | None = None
    attached_column_name: str | None = None


@dataclass(frozen=True)
class AuditGateIdentity:
    """Aggregate identity for a model's runtime audit gate."""

    binding_set_hash: str
    blocking_set_hash: str
    audits: tuple[AuditIdentity, ...]
