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
    dbt_profile: str | None = None
    dbt_prod_git_ref: str | None = None
    sqb_output_dir: str | None = None
    dry_run: bool = False
    overwrite: bool = False
    skip_dbt_debug: bool = False
    no_sql_validation: bool = False
    defer_to: str | None = None
    defer_sources_to: str | None = None
    target_range: str | None = None
    from_target: str | None = None
    to_target: str | None = None
    from_virtual_environment: str | None = None
    to_virtual_environment: str | None = None
    hard_copy: bool = False
    json: bool = False
    json_output: Path | None = None
    manifest: bool = False
    dag: str | None = None
    compile_lineage_mode: CompileLineageMode = CompileLineageMode.FAST
    profile_skip_discovery_sql_analysis: bool = False
    profile_skip_column_inference: bool = False
    profile_skip_contracts: bool = False
    profile_skip_write: bool = False
    start_cursor_ts: str | None = None
    end_cursor_ts: str | None = None
    start_cursor_int: str | None = None
    end_cursor_int: str | None = None
    no_color: bool = False
    fail_fast: bool = False
    full_refresh: bool = False
    virtual_env: str | None = None
    skip_locked: bool = False
    include_stale_upstreams: bool = False
    force: bool = False
    include_python: bool = True
    load_sources: bool | None = None
    reload: bool = False
    run_tests: bool = True
    run_audits: bool = True
    allow_snapshot_full_refresh: bool = False
    allow_snapshot_schema_change: bool = False
    allow_partial_promotion: bool = False
    allow_partial_rollback: bool = False
    rollback_checkpoint_id: str | None = None
    concurrency: int | None = None
    verbose: bool = False
    debug: bool = False
    auto_approve: bool = False
    retention_days: int | None = None
    direct_state_history_versions: int | None = None
    state_command: str | None = None
    state_checkpoint_command: str | None = None
    state_checkpoint_id: str | None = None
    state_backup_id: str | None = None
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
    fail_on_error: bool = False
    fail_on_stale: bool = False
    state: bool = False
    full: bool = False
    schema_only: bool = False
    allow_partial_diff: bool = False
    reconcile_command: str | None = None
    reconcile_model: str | None = None
    reconcile_physical_relation: str | None = None
    playground_path: str = "sqlbuild-playground"
    playground_template: str = "waffle_shop"
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
    skills_command: str | None = None
    skills_global: bool = False
    skills_target: list[str] = field(default_factory=list)
    skills_force: bool = False
    select: list[str] = field(default_factory=list)
    select_file: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    dbt_command: str | None = None
    dbt_args: list[str] = field(default_factory=list)
    vars: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CliEntrypointHandlers:
    """Injected command handlers for the CLI entrypoint."""

    run_compile: Callable[
        [
            Path | None,
            bool,
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
    run_plan: Callable[
        [
            Path | None,
            bool,
            str | None,
            str | None,
            CursorOverrides | None,
            bool,
            bool,
            str | None,
            bool | None,
            bool,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            dict[str, object],
            bool,
            bool,
        ],
        int,
    ]
    run_dbt_plan: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_run: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_build: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_test: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_scenario: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_debug: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_lineage: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_diff: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_clone: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_identity_diff: Callable[[Path | None, tuple[str, ...], bool], int]
    run_dbt_init: Callable[
        [
            Path,
            str | None,
            str | None,
            str | None,
            str | None,
            str | None,
            bool,
            bool,
            bool,
            str | None,
        ],
        int,
    ]
    run_build: Callable[
        [
            Path | None,
            bool,
            str | None,
            str | None,
            CursorOverrides | None,
            bool,
            bool,
            bool,
            str | None,
            bool | None,
            bool,
            bool,
            bool,
            bool,
            int | None,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            bool,
            dict[str, object],
            bool,
            bool,
            bool,
            bool,
            bool,
            Path | None,
        ],
        int,
    ]
    run_freshness: Callable[
        [
            Path | None,
            bool,
            bool,
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
    run_test: Callable[
        [
            Path | None,
            bool,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            dict[str, object],
            bool,
            Path | None,
        ],
        int,
    ]
    run_check: Callable[
        [
            Path | None,
            bool,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            dict[str, object],
            bool,
            Path | None,
        ],
        int,
    ]
    run_audit: Callable[
        [
            Path | None,
            bool,
            str | None,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            dict[str, object],
            bool,
            Path | None,
        ],
        int,
    ]
    run_seed: Callable[
        [
            Path | None,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            int | None,
            dict[str, object],
            bool,
            Path | None,
        ],
        int,
    ]
    run_load: Callable[
        [
            Path | None,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            int | None,
            CursorOverrides | None,
            dict[str, object],
            bool,
            Path | None,
        ],
        int,
    ]
    run_clone: Callable[
        [
            Path | None,
            bool,
            bool,
            str,
            str,
            bool,
            str | None,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            bool,
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
            bool,
        ],
        int,
    ]
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
    run_janitor: Callable[[Path | None, bool, bool, int | None, int | None], int]
    run_state: Callable[
        [Path | None, str, str | None, bool, bool, str | None, str | None, str | None, bool], int
    ]
    run_init: Callable[[Path | None], int]
    run_playground: Callable[[Path | None, str, str], int]
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
