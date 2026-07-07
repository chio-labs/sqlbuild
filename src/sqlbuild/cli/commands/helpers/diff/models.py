"""Diff command request and phase result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.diff.models import DiffExecutionResult


@dataclass(frozen=True)
class DiffCommandRequest:
    """CLI inputs for one diff command invocation."""

    project_dir: Path | None
    no_color: bool
    no_sql_validation: bool
    from_name: str
    to_name: str
    full: bool
    schema_only: bool
    bounded: str | None
    max_column_examples: int | None = None
    max_row_only_examples: int | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    verbose: bool = False
    cli_vars: dict[str, object] | None = None
    allow_partial_diff: bool = False


@dataclass(frozen=True)
class DiffInvocation:
    """Resolved project discovery and mode for diff."""

    effective_project_dir: Path
    discovered_inputs: DiscoveredProjectInputs
    is_virtual_mode: bool


@dataclass(frozen=True)
class StandardDiffPreparation:
    """Resolved standard diff adapter and compiled target projects."""

    from_target: str
    to_target: str
    adapter: BaseAdapter
    left_project: Any
    right_project: Any
    selected_names: tuple[str, ...]
    connection_config: dict[str, object]
    effective_max_column_examples: int
    effective_max_row_only_examples: int


@dataclass(frozen=True)
class VirtualDiffPreparation:
    """Resolved virtual diff adapter, connection, reporters, and sample limits."""

    from_virtual_environment: str
    to_virtual_environment: str
    adapter: BaseAdapter
    connection_config: dict[str, object]
    effective_max_column_examples: int
    effective_max_row_only_examples: int
    use_color: bool


@dataclass(frozen=True)
class VirtualDiffRunOutcome:
    """Virtual diff result plus virtual environment freshness metadata."""

    result: DiffExecutionResult
    selected_names: tuple[str, ...]
    skipped_names: tuple[str, ...]
    from_stale: tuple[str, ...]
    to_stale: tuple[str, ...]
    from_working: bool
    to_working: bool
