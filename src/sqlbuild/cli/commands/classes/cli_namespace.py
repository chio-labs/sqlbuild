"""Mutable CLI argparse namespace."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.helpers.compile.types import CompileLineageMode
from sqlbuild.compiler.lineage.types import ColumnLineageMode

_DEFAULT_VALUES: dict[str, object] = {
    "command": None,
    "project_dir": None,
    "dbt_project_dir": None,
    "dbt_profiles_dir": None,
    "dbt_target": None,
    "dbt_target_path": None,
    "dbt_profile": None,
    "dbt_prod_git_ref": None,
    "sqb_output_dir": None,
    "dry_run": False,
    "overwrite": False,
    "skip_dbt_debug": False,
    "no_sql_validation": False,
    "defer_to": None,
    "defer_clone_from": None,
    "defer_sources_to": None,
    "target": None,
    "target_range": None,
    "from_target": None,
    "to_target": None,
    "from_virtual_environment": None,
    "to_virtual_environment": None,
    "hard_copy": False,
    "json": False,
    "json_output": None,
    "manifest": False,
    "dag": None,
    "compile_lineage_mode": CompileLineageMode.FAST,
    "profile_skip_discovery_sql_analysis": False,
    "profile_skip_column_inference": False,
    "profile_skip_contracts": False,
    "profile_skip_write": False,
    "start_cursor_ts": None,
    "end_cursor_ts": None,
    "start_cursor_int": None,
    "end_cursor_int": None,
    "no_color": False,
    "fail_fast": False,
    "full_refresh": False,
    "virtual_env": None,
    "skip_locked": False,
    "include_stale_upstreams": False,
    "force": False,
    "include_python": True,
    "load_sources": None,
    "reload": False,
    "run_tests": True,
    "run_audits": True,
    "allow_snapshot_full_refresh": False,
    "allow_snapshot_schema_change": False,
    "allow_partial_promotion": False,
    "allow_partial_rollback": False,
    "rollback_checkpoint_id": None,
    "concurrency": None,
    "verbose": False,
    "debug": False,
    "auto_approve": False,
    "retention_days": None,
    "direct_state_history_versions": None,
    "state_command": None,
    "state_checkpoint_command": None,
    "state_checkpoint_id": None,
    "state_backup_id": None,
    "bounded": None,
    "max_column_examples": None,
    "max_row_only_examples": None,
    "query_sql": None,
    "query_format": "long",
    "query_limit": 20,
    "query_no_limit": False,
    "lineage_target": None,
    "lineage_format": "tree",
    "lineage_direction": "upstream",
    "lineage_depth": "all",
    "lineage_mode": ColumnLineageMode.RICH,
    "no_connection": False,
    "fail_on_error": False,
    "fail_on_stale": False,
    "state": False,
    "full": False,
    "schema_only": False,
    "allow_partial_diff": False,
    "reconcile_command": None,
    "reconcile_model": None,
    "reconcile_physical_relation": None,
    "playground_path": "sqlbuild-playground",
    "playground_template": "waffle_shop",
    "scenario_command": None,
    "scenario_selector": [],
    "scenario_retain": False,
    "scenario_local": False,
    "scenario_strict": False,
    "scenario_sync_snapshots": False,
    "scenario_refresh": False,
    "scenario_force": False,
    "scenario_max_snapshot_rows": None,
    "scenario_max_snapshot_total_rows": None,
    "scenario_max_snapshot_bytes": None,
    "scenario_max_snapshot_total_bytes": None,
    "skills_command": None,
    "skills_global": False,
    "skills_target": [],
    "skills_force": False,
    "select": [],
    "select_file": [],
    "exclude": [],
    "dbt_command": None,
    "dbt_args": [],
    "vars": {},
}


class CliNamespace:
    """Typed namespace for all CLI arguments across all commands."""

    command: str | None
    project_dir: str | None
    dbt_project_dir: str | None
    dbt_profiles_dir: str | None
    dbt_target: str | None
    dbt_target_path: str | None
    dbt_profile: str | None
    dbt_prod_git_ref: str | None
    sqb_output_dir: str | None
    dry_run: bool
    overwrite: bool
    skip_dbt_debug: bool
    no_sql_validation: bool
    defer_to: str | None
    defer_clone_from: str | None
    defer_sources_to: str | None
    target: str | None
    target_range: str | None
    from_target: str | None
    to_target: str | None
    from_virtual_environment: str | None
    to_virtual_environment: str | None
    hard_copy: bool
    json: bool
    json_output: Path | None
    manifest: bool
    dag: str | None
    compile_lineage_mode: CompileLineageMode
    profile_skip_discovery_sql_analysis: bool
    profile_skip_column_inference: bool
    profile_skip_contracts: bool
    profile_skip_write: bool
    start_cursor_ts: str | None
    end_cursor_ts: str | None
    start_cursor_int: str | None
    end_cursor_int: str | None
    no_color: bool
    fail_fast: bool
    full_refresh: bool
    virtual_env: str | None
    skip_locked: bool
    include_stale_upstreams: bool
    force: bool
    include_python: bool
    load_sources: bool | None
    reload: bool
    run_tests: bool
    run_audits: bool
    allow_snapshot_full_refresh: bool
    allow_snapshot_schema_change: bool
    allow_partial_promotion: bool
    allow_partial_rollback: bool
    rollback_checkpoint_id: str | None
    concurrency: int | None
    verbose: bool
    debug: bool
    auto_approve: bool
    retention_days: int | None
    direct_state_history_versions: int | None
    state_command: str | None
    state_checkpoint_command: str | None
    state_checkpoint_id: str | None
    state_backup_id: str | None
    bounded: str | None
    max_column_examples: int | None
    max_row_only_examples: int | None
    query_sql: str | None
    query_format: str
    query_limit: int | None
    query_no_limit: bool
    lineage_target: str | None
    lineage_format: str
    lineage_direction: str
    lineage_depth: str
    lineage_mode: ColumnLineageMode
    no_connection: bool
    fail_on_error: bool
    fail_on_stale: bool
    state: bool
    full: bool
    schema_only: bool
    allow_partial_diff: bool
    reconcile_command: str | None
    reconcile_model: str | None
    reconcile_physical_relation: str | None
    playground_path: str
    playground_template: str
    scenario_command: str | None
    scenario_selector: list[str]
    scenario_retain: bool
    scenario_local: bool
    scenario_strict: bool
    scenario_sync_snapshots: bool
    scenario_refresh: bool
    scenario_force: bool
    scenario_max_snapshot_rows: int | None
    scenario_max_snapshot_total_rows: int | None
    scenario_max_snapshot_bytes: int | None
    scenario_max_snapshot_total_bytes: int | None
    skills_command: str | None
    skills_global: bool
    skills_target: list[str]
    skills_force: bool
    select: list[str]
    select_file: list[str]
    exclude: list[str]
    dbt_command: str | None
    dbt_args: list[str]
    vars: dict[str, object]

    def __init__(self) -> None:
        for name, value in _DEFAULT_VALUES.items():
            setattr(self, name, value.copy() if isinstance(value, (dict, list)) else value)
