"""Data models and handler protocol relationships for CLI entry dispatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
    from sqlbuild.cli.commands.models import (
        AuditCommandRequest,
        BuildCommandRequest,
        CheckCommandRequest,
        CloneCommandRequest,
        ContractCommandRequest,
        CostCommandRequest,
        DbtInitCommandRequest,
        DiffCommandRequest,
        FreshnessCommandRequest,
        JanitorCommandRequest,
        LoadCommandRequest,
        PlanCommandRequest,
        PlaygroundCommandRequest,
        PromoteCommandRequest,
        RollbackCommandRequest,
        RulesCommandRequest,
        ScenarioCaptureCommandRequest,
        ScenarioTestCommandRequest,
        SeedCommandRequest,
        TestCommandRequest,
    )
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

    from .compile_models import CompileCommandRequest


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
    run_cost: Callable[[CostCommandRequest], int]
    run_dag: DagCommandHandler
    run_plan: Callable[[PlanCommandRequest], int]
    run_dbt_plan: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_run: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_build: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_debug: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_init: Callable[[DbtInitCommandRequest], int]
    run_build: Callable[[BuildCommandRequest], int]
    run_freshness: Callable[[FreshnessCommandRequest], int]
    run_test: Callable[[TestCommandRequest], int]
    run_check: Callable[[CheckCommandRequest], int]
    run_audit: Callable[[AuditCommandRequest], int]
    run_seed: Callable[[SeedCommandRequest], int]
    run_load: Callable[[LoadCommandRequest], int]
    run_clone: Callable[[CloneCommandRequest], int]
    run_diff: Callable[[DiffCommandRequest], int]
    run_reconcile: ReconcileCommandHandler
    run_promote: Callable[[PromoteCommandRequest], int]
    run_rollback: Callable[[RollbackCommandRequest], int]
    run_query: QueryCommandHandler
    run_debug: DebugCommandHandler
    run_lineage: LineageCommandHandler
    run_janitor: Callable[[JanitorCommandRequest], int]
    run_state: StateCommandHandler
    run_init: Callable[[Path | None], int]
    run_playground: Callable[[PlaygroundCommandRequest], int]
    run_skills_update: SkillsUpdateCommandHandler
    run_format: FormatCommandHandler
    run_scenario: Callable[[ScenarioTestCommandRequest], int]
    run_scenario_capture: Callable[[ScenarioCaptureCommandRequest], int]
    run_rules: Callable[[RulesCommandRequest], int]
    run_scope: ScopeCommandHandler
    run_contract: Callable[[ContractCommandRequest], int] | None = None
