"""Janitor command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.janitor.models import JanitorPlan
from sqlbuild.virtual.state.models import (
    CheckpointRetentionInspection,
    DetachedVirtualEnvironmentInspection,
    ExpiredVirtualEnvironmentInspection,
    StateJanitorInspection,
)


@dataclass(frozen=True)
class JanitorCommandRequest:
    """CLI inputs for one janitor command invocation."""

    project_dir: Path | None
    no_color: bool = False
    auto_approve: bool = False
    retention_days: int | None = None
    direct_state_history_versions: int | None = None


@dataclass(frozen=True)
class JanitorInvocation:
    """Resolved project discovery and output context for janitor."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    use_color: bool


@dataclass(frozen=True)
class JanitorSettings:
    """Validated effective janitor settings."""

    retention_days: int
    direct_state_history_versions: int


@dataclass(frozen=True)
class JanitorCompileContext:
    """Compiled project and adapter context for janitor."""

    adapter_name: str
    adapter: BaseAdapter
    project: CompiledProject
    connection_config: dict[str, object]


@dataclass(frozen=True)
class JanitorConnectionContext:
    """Janitor warehouse connection handle."""

    connection: object


@dataclass(frozen=True)
class JanitorRetentionInspection:
    """Retention inspection results used to build a janitor plan."""

    checkpoint: CheckpointRetentionInspection | None
    detached_environment: DetachedVirtualEnvironmentInspection | None
    expired_environment: ExpiredVirtualEnvironmentInspection | None
    state: StateJanitorInspection | None
    unsuffixed_virtual_environment_name: str | None


@dataclass(frozen=True)
class JanitorPlanningResult:
    """Built janitor plan."""

    plan: JanitorPlan
