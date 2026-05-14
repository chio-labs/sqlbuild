"""CLI entry models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.planner.models import CursorOverrides


@dataclass
class CliNamespace:
    """Typed namespace for all CLI arguments across all commands."""

    command: str | None = None
    project_dir: str | None = None
    dbt_project_dir: str | None = None
    dbt_profiles_dir: str | None = None
    dbt_target: str | None = None
    dbt_target_path: str | None = None
    no_sql_validation: bool = False
    defer_to: str | None = None
    environment_range: str | None = None
    from_environment: str | None = None
    to_environment: str | None = None
    hard_copy: bool = False
    json: bool = False
    manifest: bool = False
    compile_lineage_mode: CompileLineageMode = CompileLineageMode.FAST
    start_cursor_ts: str | None = None
    end_cursor_ts: str | None = None
    start_cursor_int: str | None = None
    end_cursor_int: str | None = None
    no_color: bool = False
    fail_fast: bool = False
    full_refresh: bool = False
    concurrency: int | None = None
    verbose: bool = False
    debug: bool = False
    auto_approve: bool = False
    retention_days: int | None = None
    bounded: str | None = None
    max_column_examples: int | None = None
    max_row_only_examples: int | None = None
    query_sql: str | None = None
    query_format: str = "long"
    query_limit: int | None = 20
    query_no_limit: bool = False
    lineage_target: str | None = None
    lineage_format: str = "tree"
    lineage_direction: str = "upstream"
    lineage_depth: str = "all"
    lineage_mode: ColumnLineageMode = ColumnLineageMode.RICH
    no_connection: bool = False
    full: bool = False
    schema_only: bool = False
    playground_path: str = "sqlbuild-playground"
    scenario_command: str | None = None
    scenario_selector: list[str] = field(default_factory=list)
    scenario_retain: bool = False
    scenario_local: bool = False
    scenario_strict: bool = False
    scenario_sync_snapshots: bool = False
    scenario_refresh: bool = False
    scenario_force: bool = False
    scenario_max_snapshot_rows: int | None = None
    scenario_max_snapshot_total_rows: int | None = None
    scenario_max_snapshot_bytes: int | None = None
    scenario_max_snapshot_total_bytes: int | None = None
    select: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    dbt_command: str | None = None
    dbt_args: list[str] = field(default_factory=list)
    vars: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CliEntrypointHandlers:
    """Injected command handlers for the CLI entrypoint."""

    run_compile: Callable[
        [Path | None, bool, str | None, bool, bool, bool, CompileLineageMode, dict[str, object]],
        int,
    ]
    run_plan: Callable[
        [
            Path | None,
            bool,
            str | None,
            CursorOverrides | None,
            bool,
            bool,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            dict[str, object],
        ],
        int,
    ]
    run_dbt_plan: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_run: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_build: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_test: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_debug: Callable[[Path | None, tuple[str, ...], bool], int]
    run_build: Callable[
        [
            Path | None,
            bool,
            str | None,
            CursorOverrides | None,
            bool,
            bool,
            bool,
            int | None,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            bool,
            dict[str, object],
        ],
        int,
    ]
    run_run: Callable[
        [
            Path | None,
            bool,
            str | None,
            CursorOverrides | None,
            bool,
            bool,
            bool,
            int | None,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            bool,
            dict[str, object],
        ],
        int,
    ]
    run_test: Callable[
        [Path | None, bool, bool, tuple[str, ...], tuple[str, ...], dict[str, object]], int
    ]
    run_audit: Callable[
        [Path | None, bool, str | None, bool, tuple[str, ...], tuple[str, ...], dict[str, object]],
        int,
    ]
    run_seed: Callable[
        [Path | None, bool, tuple[str, ...], tuple[str, ...], dict[str, object]], int
    ]
    run_clone: Callable[
        [
            Path | None,
            bool,
            bool,
            str,
            str,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            dict[str, object],
        ],
        int,
    ]
    run_diff: Callable[
        [
            Path | None,
            bool,
            bool,
            str,
            str,
            bool,
            bool,
            str | None,
            int | None,
            int | None,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            dict[str, object],
        ],
        int,
    ]
    run_query: Callable[[Path | None, str | None, str, int | None], int]
    run_debug: Callable[[Path | None, bool, bool, bool], int]
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
    run_janitor: Callable[[Path | None, bool, bool, int | None], int]
    run_playground: Callable[[Path | None, str], int]
    run_scenario: Callable[
        [
            Path | None,
            bool,
            bool,
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
        ],
        int,
    ]
    run_scenario_capture: Callable[
        [
            Path | None,
            bool,
            bool,
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
