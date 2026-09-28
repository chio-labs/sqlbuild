"""Structured graph facts shared by compile validation and execution planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.graph.types import HookReadType


@dataclass(frozen=True)
class AttachedAuditGateEdge:
    """One ordering edge: the gated node waits for a resource its attached audit reads."""

    audit_name: str
    target: CompiledObjectKey
    gated: CompiledObjectKey
    read: CompiledObjectKey


@dataclass(frozen=True)
class HookReadEdge:
    """One ordering edge: a model waits for a resource one of its hooks reads."""

    hook_name: str
    gated: CompiledObjectKey
    read: CompiledObjectKey
    hook_type: HookReadType = HookReadType.PYTHON
    hook_path: Path | None = None

    @property
    def label(self) -> str:
        """Return how diagnostics name the hook, such as ``SQL hook 'grant_access'``."""

        if self.hook_type is HookReadType.INLINE_SQL:
            return f"inline SQL hook {self.hook_name}"
        return f"{self.hook_type.value} hook '{self.hook_name}'"
