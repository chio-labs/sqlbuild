"""Internal Python-node execution result models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.python_nodes.types import (
    PythonNodeFanInAction,
    PythonNodeKind,
    PythonNodeStatus,
    SkipMode,
)


@dataclass(frozen=True)
class PythonNodeResult:
    """User-facing successful result returned by a Python node."""

    payload: object | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    materialized: bool | None = None


@dataclass(frozen=True)
class PythonNodeSkipResult:
    """User-facing skip signal returned by a Python node."""

    reason: str
    mode: SkipMode = SkipMode.DOWNSTREAM
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PythonNodeExecutionResult:
    """Normalized execution outcome for one Python node."""

    node_name: str
    kind: PythonNodeKind
    status: PythonNodeStatus
    payload: object | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    materialized: bool | None = None
    skip_mode: SkipMode | None = None
    skip_reason: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class PythonNodeFanInDecision:
    """Scheduler decision for a node after all upstream outcomes are known."""

    action: PythonNodeFanInAction
    reason: str | None = None
