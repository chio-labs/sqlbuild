"""Executor pipeline domain models."""

from __future__ import annotations

from dataclasses import dataclass

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
