"""Load command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.spec.models.source import SourceEntry


@dataclass(frozen=True)
class LoadCommandRequest:
    """CLI inputs for one load command invocation."""

    project_dir: Path | None
    no_color: bool = False
    selected_target: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    reload: bool = False
    concurrency: int | None = None
    cursor_overrides: CursorOverrides | None = None
    cli_vars: dict[str, object] | None = None
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class LoadInvocation:
    """Resolved project, selected sources, and output context for load."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    selected_sources: tuple[SourceEntry, ...]
    reference_sources: tuple[SourceEntry, ...]
    use_color: bool
    progress_stream: TextIO


@dataclass(frozen=True)
class LoadExecutionPreparation:
    """Prepared adapter, connection, runtime, and execution settings."""

    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    target_name: str | None
    effective_vars: dict[str, object]
    run_id: str
    effective_cursor_overrides: CursorOverrides
    effective_concurrency: int
    provider_session: Any


@dataclass(frozen=True)
class LoadRunOutcome:
    """Load execution results, elapsed time, and summary counts."""

    results: tuple[LoadExecutionResult, ...]
    elapsed: float
    success_count: int
    fail_count: int
    skip_count: int
