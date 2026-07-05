"""CLI entry models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.cli.commands.helpers.audit.models import AuditCommandRequest
from sqlbuild.cli.commands.helpers.build.models import BuildCommandRequest
from sqlbuild.cli.commands.helpers.check.models import CheckCommandRequest
from sqlbuild.cli.commands.helpers.clone.models import CloneCommandRequest
from sqlbuild.cli.commands.helpers.compile.types import CompileLineageMode
from sqlbuild.cli.commands.helpers.dbt_init.models import DbtInitCommandRequest
from sqlbuild.cli.commands.helpers.diff.models import DiffCommandRequest
from sqlbuild.cli.commands.helpers.entry.namespace import CliNamespace  # noqa: F401
from sqlbuild.cli.commands.helpers.janitor.models import JanitorCommandRequest
from sqlbuild.cli.commands.helpers.load.models import LoadCommandRequest
from sqlbuild.cli.commands.helpers.plan.models import PlanCommandRequest
from sqlbuild.cli.commands.helpers.playground.models import PlaygroundCommandRequest
from sqlbuild.cli.commands.helpers.seed.models import SeedCommandRequest
from sqlbuild.cli.commands.helpers.test.models import TestCommandRequest
from sqlbuild.compiler.lineage.types import ColumnLineageMode


@dataclass(frozen=True)
class CliEntrypointHandlers:
    """Injected command handlers for the CLI entrypoint."""

    run_compile: Callable[
        [
            Path | None,
            bool,
            str | None,
            str | None,
            bool,
            bool,
            str | None,
            bool,
            CompileLineageMode,
            dict[str, object],
            bool,
            bool,
            bool,
            bool,
        ],
        int,
    ]
    run_dag: Callable[[Path | None, bool, bool, dict[str, object]], int]
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
        [
            Path | None,
            bool,
            bool,
            str | None,
            tuple[str, ...],
            tuple[str, ...],
            dict[str, object],
            bool,
            Path | None,
            bool,
            bool,
            bool,
            str | None,
        ],
        int,
    ]
    run_test: Callable[[TestCommandRequest], int]
    run_check: Callable[[CheckCommandRequest], int]
    run_audit: Callable[[AuditCommandRequest], int]
    run_seed: Callable[[SeedCommandRequest], int]
    run_load: Callable[[LoadCommandRequest], int]
    run_clone: Callable[[CloneCommandRequest], int]
    run_diff: Callable[[DiffCommandRequest], int]
    run_reconcile: Callable[
        [
            Path | None,
            bool,
            str | None,
            str | None,
            str | None,
            str | None,
            str | None,
            bool,
            dict[str, object],
        ],
        int,
    ]
    run_promote: Callable[
        [
            Path | None,
            bool,
            bool,
            str,
            str,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            bool,
            bool,
            dict[str, object],
        ],
        int,
    ]
    run_rollback: Callable[
        [
            Path | None,
            bool,
            bool,
            str | None,
            bool,
            str | None,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            bool,
            dict[str, object],
        ],
        int,
    ]
    run_query: Callable[[Path | None, str | None, str | None, str, int | None], int]
    run_debug: Callable[[Path | None, bool, bool, str | None, bool], int]
    run_lineage: Callable[
        [
            Path | None,
            bool,
            str | None,
            str,
            str,
            str,
            tuple[str, ...],
            tuple[str, ...],
            ColumnLineageMode,
            dict[str, object],
        ],
        int,
    ]
    run_janitor: Callable[[JanitorCommandRequest], int]
    run_state: Callable[
        [Path | None, str, str | None, bool, bool, str | None, str | None, str | None, bool], int
    ]
    run_init: Callable[[Path | None], int]
    run_playground: Callable[[PlaygroundCommandRequest], int]
    run_skills_update: Callable[[Path | None, bool, tuple[str, ...], bool], int]
    run_scenario: Callable[
        [
            Path | None,
            bool,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            int | None,
            int | None,
            int | None,
            int | None,
            bool,
            Path | None,
        ],
        int,
    ]
    run_scenario_capture: Callable[
        [
            Path | None,
            bool,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            bool,
            int | None,
            int | None,
            int | None,
            int | None,
        ],
        int,
    ]
