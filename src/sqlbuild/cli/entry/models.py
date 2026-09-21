"""Data models and handler relationships for CLI entry dispatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.types import (
    DagCommandHandler,
    DebugCommandHandler,
    FormatCommandHandler,
    LineageCommandHandler,
    QueryCommandHandler,
    ReconcileCommandHandler,
    ScopeCommandHandler,
    SkillsUpdateCommandHandler,
    StateCommandHandler,
)
from sqlbuild.cli.compile.models import CompileCommandRequest


@dataclass(frozen=True)
class SelectorFileSummary:
    """Non-expanded provenance for one selector file."""

    path: Path
    selector_count: int


@dataclass(frozen=True)
class SelectorInputs:
    """Expanded selectors paired with selector-file provenance."""

    selectors: tuple[str, ...]
    files: tuple[SelectorFileSummary, ...]


@dataclass(frozen=True)
class ParsedCliInvocation:
    """Outcome of parsing CLI arguments: either a namespace or an exit code."""

    args: CliNamespace | None
    exit_code: int | None


@dataclass(frozen=True)
class CliEntrypointHandlers:
    """Injected command handlers for the CLI entrypoint."""

    run_compile: Callable[[CompileCommandRequest], int]
    run_cost: Callable[..., int]
    run_dag: DagCommandHandler
    run_plan: Callable[..., int]
    run_dbt_plan: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_run: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_build: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_debug: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_init: Callable[..., int]
    run_build: Callable[..., int]
    run_freshness: Callable[..., int]
    run_test: Callable[..., int]
    run_check: Callable[..., int]
    run_audit: Callable[..., int]
    run_seed: Callable[..., int]
    run_load: Callable[..., int]
    run_clone: Callable[..., int]
    run_diff: Callable[..., int]
    run_reconcile: ReconcileCommandHandler
    run_promote: Callable[..., int]
    run_rollback: Callable[..., int]
    run_query: QueryCommandHandler
    run_debug: DebugCommandHandler
    run_lineage: LineageCommandHandler
    run_janitor: Callable[..., int]
    run_state: StateCommandHandler
    run_init: Callable[[Path | None], int]
    run_playground: Callable[..., int]
    run_skills_update: SkillsUpdateCommandHandler
    run_format: FormatCommandHandler
    run_scenario: Callable[..., int]
    run_scenario_capture: Callable[..., int]
    run_rules: Callable[..., int]
    run_scope: ScopeCommandHandler
    run_contract: Callable[..., int] | None = None
