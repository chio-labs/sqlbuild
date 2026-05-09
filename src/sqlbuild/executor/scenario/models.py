"""Scenario executor domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.shared.types import ExecutionStatus


@dataclass(frozen=True)
class ScenarioFixtureExecutionResult:
    """Outcome of materializing one scenario fixture relation."""

    scenario_name: str
    kind: ScenarioArtifactKind
    logical_name: str
    target_relation: str
    status: ExecutionStatus
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioCleanupTarget:
    """One planned scenario-owned relation selected for cleanup."""

    kind: ScenarioArtifactKind
    logical_name: str
    target_relation: str


@dataclass(frozen=True)
class ScenarioCleanupExecutionResult:
    """Outcome of dropping planned scenario-owned relations."""

    scenario_name: str
    status: ExecutionStatus
    targets: tuple[ScenarioCleanupTarget, ...] = field(default_factory=tuple)
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioExpectedCheckExecutionResult:
    """Outcome of comparing one scenario model relation to expected SQL."""

    scenario_name: str
    model_name: str
    status: ExecutionStatus
    actual_row_count: int = 0
    expected_row_count: int = 0
    mismatched_row_count: int = 0
    error_message: str | None = None


@dataclass(frozen=True)
class ScenarioAssertionCheckExecutionResult:
    """Outcome of executing one zero-row scenario assertion."""

    scenario_name: str
    name: str
    status: ExecutionStatus
    failing_row_count: int = 0
    sample_rows: tuple[tuple[object, ...], ...] = field(default_factory=tuple)
    error_message: str | None = None
