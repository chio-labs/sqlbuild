"""Executor pipeline domain models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildCustomizations,
    BuildInitialState,
    BuildRuntimeParams,
)
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback


@dataclass(frozen=True)
class AuditPipelineCallbacks:
    """Optional connection and item callbacks for standalone audit execution."""

    on_connection_start: Callable[[int], None] | None = None
    on_connection_complete: ConnectionElapsedCallback | None = None
    on_connection_error: ConnectionElapsedCallback | None = None
    on_audit_start: Callable[[AuditPlanEntry], None] | None = None
    on_audit_physical_complete: Callable[[AuditExecutionResult], None] | None = None
    on_audit_complete: Callable[[AuditExecutionResult], None] | None = None
    on_audit_error: Callable[[AuditPlanEntry], None] | None = None


@dataclass(frozen=True)
class ResolvedBuildInputs:
    """Fully-resolved runtime bundles for one build pipeline run."""

    runtime: BuildRuntimeParams
    callbacks: BuildCallbacks
    customizations: BuildCustomizations
    initial_state: BuildInitialState


@dataclass(frozen=True)
class BuildConnectionPreparation:
    """Disjoint connection and schema preparation results."""

    scheduler_connection: Any
    worker_connections: tuple[Any, ...]
    connection_seconds: float
    schema_seconds: float | None
