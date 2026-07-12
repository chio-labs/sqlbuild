"""Scenario CLI runner request and context models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledSqlScenario
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import CompilePipelineResult


@dataclass(frozen=True)
class ScenarioRunOutputContext:
    """Progress stream and JSON output settings for one scenario CLI run."""

    progress_stream: TextIO
    use_color: bool
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class ScenarioSnapshotLimitInputs:
    """CLI snapshot capture-limit overrides for one scenario run."""

    max_snapshot_rows: int | None = None
    max_snapshot_total_rows: int | None = None
    max_snapshot_bytes: int | None = None
    max_snapshot_total_bytes: int | None = None
    force: bool = False


@dataclass(frozen=True)
class ScenarioTestCommandRequest:
    """CLI inputs for one `sqb scenario test` invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selectors: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    retain: bool = False
    local: bool = False
    strict: bool = False
    sync_snapshots: bool = False
    refresh: bool = False
    limit_inputs: ScenarioSnapshotLimitInputs = ScenarioSnapshotLimitInputs()
    json_output: bool = False
    json_output_path: Path | None = None


@dataclass(frozen=True)
class ScenarioCaptureCommandRequest:
    """CLI inputs for one `sqb scenario capture` invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selectors: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    retain: bool = False
    limit_inputs: ScenarioSnapshotLimitInputs = ScenarioSnapshotLimitInputs()


@dataclass(frozen=True)
class LocalSnapshotSyncInputs:
    """Resolved project, adapters, and scenarios for a local snapshot sync run."""

    project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    local_pipeline_result: CompilePipelineResult
    local_scenarios: tuple[CompiledSqlScenario, ...]
    local_adapter: BaseAdapter
    project_adapter: BaseAdapter
    project_adapter_name: str
    capture_dialect: str
    project_connection_config: dict[str, object]
    project_name: str
    no_sql_validation: bool
    refresh: bool
