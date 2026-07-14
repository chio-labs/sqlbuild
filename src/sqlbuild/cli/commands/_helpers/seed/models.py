"""Seed command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.build.models import SeedExecutionResult


@dataclass(frozen=True)
class SeedCommandRequest:
    """CLI inputs for one seed command invocation."""

    project_dir: Path | None
    no_color: bool = False
    selected_target: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    concurrency: int | None = None
    cli_vars: dict[str, object] | None = None
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class SeedInvocation:
    """Resolved project, adapter, connection, and output context for seed."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    use_color: bool
    progress_stream: TextIO


@dataclass(frozen=True)
class SeedExecutionPreparation:
    """Prepared seed execution settings and compiled pipeline."""

    pipeline_result: CompilePipelineResult
    effective_concurrency: int


@dataclass(frozen=True)
class SeedRunOutcome:
    """Seed execution results and elapsed time."""

    results: tuple[SeedExecutionResult, ...]
    elapsed: float
