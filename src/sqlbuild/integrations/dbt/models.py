"""dbt interop domain models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild._native import DbtLsNode, DbtNodeMessage


@dataclass(frozen=True)
class DbtCliOptions:
    """Resolved dbt CLI options shared by dbt commands."""

    project_dir: Path | None = None
    profiles_dir: Path | None = None
    target: str | None = None
    target_path: Path | None = None
    vars: str | None = None
    state: Path | None = None
    defer: bool = False


@dataclass(frozen=True)
class SelectedDbtProfileOutput:
    """Selected dbt profile target output before rendering."""

    profile_name: str
    target_name: str
    output: dict[str, object]


@dataclass(frozen=True)
class ResolvedDbtProfileOutput:
    """Rendered dbt profile target output."""

    project_dir: Path
    profiles_dir: Path
    profile_name: str
    target_name: str
    output: dict[str, object]

    @property
    def adapter_type(self) -> str:
        """Return the dbt adapter type from the rendered output."""

        value: object | None = self.output.get("type")
        return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class NormalizedDbtProfileConnection:
    """Rendered dbt profile output normalized for SQLBuild."""

    adapter: str
    connection: dict[str, object]
    target_schema: str | None = None
    target_database: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtInitProgressCallbacks:
    """Optional progress hooks for `sqb dbt init` phases."""

    start: Callable[[str], None] | None = None
    complete: Callable[[str], None] | None = None


@dataclass(frozen=True)
class DbtInitRequest:
    """Request to initialize a SQLBuild project from a dbt project."""

    cwd: Path
    dbt_project_dir: Path
    profiles_dir: Path | None
    profile_name: str | None
    target_name: str | None
    sqb_output_dir: Path | None
    dry_run: bool = False
    overwrite: bool = False
    skip_dbt_debug: bool = False
    progress_callbacks: DbtInitProgressCallbacks = field(default_factory=DbtInitProgressCallbacks)


@dataclass(frozen=True)
class DbtInitResult:
    """Result from `sqb dbt init`."""

    output_dir: Path
    project_file: Path
    project_name: str
    adapter: str
    target_name: str
    profile_name: str
    toml: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    dry_run: bool = False


@dataclass(frozen=True)
class DbtCommandResult:
    """Completed dbt command output."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class DbtNodeExecutionResult:
    """One dbt node execution result parsed from JSON logs."""

    unique_id: str
    resource_type: str
    node_name: str
    status: str
    index: int | None
    total: int | None
    execution_time: float | None
    materialized: str | None = None
    relation_name: str | None = None
    database: str | None = None
    schema: str | None = None
    node_checksum: str | None = None
    messages: tuple[DbtNodeMessage, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DbtLsResult:
    """Parsed result from one dbt ls invocation."""

    nodes: tuple[DbtLsNode, ...]
    command: DbtCommandResult
