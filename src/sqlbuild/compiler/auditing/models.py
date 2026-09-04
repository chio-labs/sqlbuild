"""Auditing identity models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.auditing.types import AuditSeverity


@dataclass(frozen=True)
class AuditIdentity:
    """Stable identity values for one planned audit binding."""

    binding_key: str
    audit_name: str
    definition_fingerprint: str
    execution_fingerprint: str
    severity: AuditSeverity
    run_scope_phase: str
    attachment_kind: str
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    always_run: bool = False


@dataclass(frozen=True)
class AuditGateIdentity:
    """Aggregate identity for a model's runtime audit gate."""

    binding_set_hash: str
    blocking_set_hash: str
    audits: tuple[AuditIdentity, ...]
