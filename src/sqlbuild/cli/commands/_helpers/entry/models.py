"""CLI entry models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.cli.commands._helpers.audit.models import AuditCommandRequest
from sqlbuild.cli.commands._helpers.build.models import BuildCommandRequest
from sqlbuild.cli.commands._helpers.check.models import CheckCommandRequest
from sqlbuild.cli.commands._helpers.clone.models import CloneCommandRequest
from sqlbuild.cli.commands._helpers.compile.models import CompileCommandRequest
from sqlbuild.cli.commands._helpers.dbt_init.models import DbtInitCommandRequest
from sqlbuild.cli.commands._helpers.diff.models import DiffCommandRequest
from sqlbuild.cli.commands._helpers.entry.types import (
    DagCommandHandler,
    DebugCommandHandler,
    LineageCommandHandler,
    QueryCommandHandler,
    ReconcileCommandHandler,
    SkillsUpdateCommandHandler,
    StateCommandHandler,
)
from sqlbuild.cli.commands._helpers.freshness.models import FreshnessCommandRequest
from sqlbuild.cli.commands._helpers.janitor.models import JanitorCommandRequest
from sqlbuild.cli.commands._helpers.load.models import LoadCommandRequest
from sqlbuild.cli.commands._helpers.plan.models import PlanCommandRequest
from sqlbuild.cli.commands._helpers.playground.models import PlaygroundCommandRequest
from sqlbuild.cli.commands._helpers.promote.models import PromoteCommandRequest
from sqlbuild.cli.commands._helpers.rollback.models import RollbackCommandRequest
from sqlbuild.cli.commands._helpers.scenario.models import (
    ScenarioCaptureCommandRequest,
    ScenarioTestCommandRequest,
)
from sqlbuild.cli.commands._helpers.seed.models import SeedCommandRequest
from sqlbuild.cli.commands._helpers.test.models import TestCommandRequest
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace


@dataclass(frozen=True)
class ParsedCliInvocation:
    """Outcome of parsing CLI arguments: either a namespace or an exit code."""

    args: CliNamespace | None
    exit_code: int | None


@dataclass(frozen=True)
class CliEntrypointHandlers:
    """Injected command handlers for the CLI entrypoint."""

    run_compile: Callable[[CompileCommandRequest], int]
    run_dag: DagCommandHandler
    run_plan: Callable[[PlanCommandRequest], int]
    run_dbt_plan: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_run: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_build: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_test: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_scenario: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_debug: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_lineage: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_diff: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_clone: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_init: Callable[[DbtInitCommandRequest], int]
    run_build: Callable[[BuildCommandRequest], int]
    run_freshness: Callable[
        [FreshnessCommandRequest],
        int,
    ]
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
    run_scenario: Callable[[ScenarioTestCommandRequest], int]
    run_scenario_capture: Callable[[ScenarioCaptureCommandRequest], int]
