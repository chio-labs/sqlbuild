"""Executor pipeline domain models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildCustomizations,
    BuildInitialState,
    BuildRuntimeParams,
)


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
