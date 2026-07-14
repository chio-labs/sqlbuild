"""Clone command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ClonePipelineResult
from sqlbuild.executor.clone.models import CloneExecutionResult


@dataclass(frozen=True)
class CloneCommandRequest:
    """CLI inputs for one clone command invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    origin_target_name: str
    destination_target_name: str
    hard_copy: bool
    virtual_env: str | None = None
    skip_locked: bool = False
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    cli_vars: dict[str, object] | None = None


@dataclass(frozen=True)
class CloneInvocation:
    """Resolved project, adapter, and output context for clone."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter_name: str
    adapter: BaseAdapter
    use_color: bool
    progress_stream: TextIO


@dataclass(frozen=True)
class CloneConnectionContext:
    """Origin and destination connection configuration and handles."""

    origin_connection_config: dict[str, object]
    destination_connection_config: dict[str, object]
    origin_connection: Any
    destination_connection: Any


@dataclass(frozen=True)
class CloneExecutionPreparation:
    """Prepared standard clone pipeline and selected destination entries."""

    pipeline_result: ClonePipelineResult


@dataclass(frozen=True)
class CloneRunOutcome:
    """Standard clone execution result and elapsed time."""

    result: CloneExecutionResult
    elapsed: float
