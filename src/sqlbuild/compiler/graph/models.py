"""Structured graph facts shared by compile validation and execution planning."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledObjectKey


@dataclass(frozen=True)
class AttachedAuditGateEdge:
    """One ordering edge: the gated node waits for a resource its attached audit reads."""

    audit_name: str
    target: CompiledObjectKey
    gated: CompiledObjectKey
    read: CompiledObjectKey
