"""Shared e2e test helpers for CLI command tests."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from shutil import copytree
from typing import Any, Protocol

REPO_ROOT: Path = Path(__file__).resolve().parents[8]
WAFFLE_SHOP_DIR: Path = REPO_ROOT / "tests" / "e2e" / "fixtures" / "waffle_shop"
SOURCE_LOADER_STRATEGIES_DIR: Path = (
    REPO_ROOT / "tests" / "e2e" / "fixtures" / "source_loader_strategies"
)


class RealAdapterDependencyBaselineCase(Protocol):
    description: str
    schema_prefix: str
    command: tuple[str, ...]
    expected_stdout_fragments: tuple[str, ...]
    expected_absent_stdout_fragments: tuple[str, ...]
    expected_upstream_rows: tuple[tuple[object, ...], ...]
    expected_downstream_rows: tuple[tuple[object, ...], ...]
    expected_fingerprint_rows: tuple[tuple[object, ...], ...]
    expected_return_code: int


def assert_real_adapter_dependency_baseline_case(
    *,
    tmp_path: Path,
    test_case: RealAdapterDependencyBaselineCase,
    project_name: str,
    dev_schema_name: str,
    prod_schema_name: str,
    project_toml: str,
    ensure_schema_ready: Callable[[str], None],
    cleanup_schema: Callable[[str], None],
    fetch_rows: Callable[[str], tuple[tuple[object, ...], ...]],
    relation_name: Callable[[str, str], str],
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": project_toml,
            "models/upstream.sql": (
                "MODEL (materialized table);\n\nSELECT 1 AS id, 900 AS amount\n"
            ),
            "models/downstream.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT id, amount AS downstream_amount FROM __ref("upstream")\n'
            ),
        },
    )
    try:
        ensure_schema_ready(dev_schema_name)
        ensure_schema_ready(prod_schema_name)
        (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
        prod_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--select", "upstream"),
            project_dir=project_dir,
        )
        assert prod_result.returncode == 0, prod_result.stdout + prod_result.stderr
        (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        expected_fragment: str
        for expected_fragment in test_case.expected_stdout_fragments:
            assert expected_fragment in result.stdout
        absent_fragment: str
        for absent_fragment in test_case.expected_absent_stdout_fragments:
            assert absent_fragment not in result.stdout
        assert (
            fetch_rows(
                f"SELECT id, amount FROM {relation_name(dev_schema_name, 'upstream')} ORDER BY id"
            )
            == test_case.expected_upstream_rows
        )
        assert (
            fetch_rows(
                "SELECT id, downstream_amount FROM "
                f"{relation_name(dev_schema_name, 'downstream')} ORDER BY id"
            )
            == test_case.expected_downstream_rows
        )
        assert (
            fetch_rows(
                "SELECT node_type, node_name FROM "
                f"{relation_name(dev_schema_name, '_sqlbuild_fingerprints')} "
                "WHERE node_type = 'model' ORDER BY node_name"
            )
            == test_case.expected_fingerprint_rows
        )
    finally:
        cleanup_schema(dev_schema_name)
        cleanup_schema(prod_schema_name)


def prepare_waffle_shop(tmp_path: Path) -> Path:
    """Copy waffle shop project to tmp dir with a fresh DuckDB target path."""

    project_dir: Path = tmp_path / "waffle_shop"
    copytree(WAFFLE_SHOP_DIR, project_dir)

    db_path: Path = project_dir / "waffle_shop.duckdb"
    if db_path.exists():
        db_path.unlink()

    return project_dir


def prepare_source_loader_strategies(
    *,
    tmp_path: Path,
    project_toml: str | None = None,
) -> Path:
    """Copy source-loader strategy fixture to tmp dir with optional warehouse config."""

    project_dir: Path = tmp_path / "source_loader_strategies"
    copytree(SOURCE_LOADER_STRATEGIES_DIR, project_dir)

    db_path: Path = project_dir / "source_loader_strategies.duckdb"
    if db_path.exists():
        db_path.unlink()

    if project_toml is not None:
        (project_dir / "sqlbuild_project.toml").write_text(project_toml, encoding="utf-8")

    return project_dir


def prepare_inline_project(
    *, tmp_path: Path, project_name: str, repo_files: Mapping[str, str]
) -> Path:
    """Write an inline-authored project to tmp dir and return its root path."""

    project_dir: Path = tmp_path / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    relative_path: str
    contents: str
    for relative_path, contents in repo_files.items():
        file_path: Path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")

    return project_dir


def prepare_dbt_profile_workspace(*, tmp_path: Path, profiles_yml: str) -> Path:
    """Write a minimal dbt project/profiles pair for dbt-profile E2Es."""

    workspace: Path = tmp_path / "workspace"
    dbt_project_dir: Path = workspace / "dbt_project"
    profiles_dir: Path = workspace / "profiles"
    (dbt_project_dir / "models").mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "target-path: target\n"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    (profiles_dir / "profiles.yml").write_text(profiles_yml, encoding="utf-8")
    write_dbt_profile_orders_model(workspace=workspace, order_id=1)
    _init_workspace_git_repo(workspace=workspace, production_ref="main")
    return workspace


def _init_workspace_git_repo(*, workspace: Path, production_ref: str) -> None:
    """Initialize a git repo with a committed production ref on a side branch.

    dbt reuse_from (scaffolded by sqb dbt init) archives the configured git_ref to
    plan dependency-baseline reuse, so the dbt project must be committed under a ref
    that is not the active branch.
    """

    def run_git(*args: str) -> None:
        subprocess.run(("git", *args), cwd=workspace, capture_output=True, check=True, text=True)

    run_git("init")
    run_git("config", "user.email", "sqlbuild@example.invalid")
    run_git("config", "user.name", "SQLBuild Test")
    run_git("checkout", "-b", "work")
    run_git("add", ".")
    run_git("commit", "-m", "baseline")
    run_git("branch", production_ref)


def write_dbt_profile_orders_model(*, workspace: Path, order_id: int) -> None:
    """Write the mutable dbt model used by adapter dbt-profile E2Es."""

    (workspace / "dbt_project" / "models" / "dbt_orders.sql").write_text(
        f"select {order_id} as order_id\n",
        encoding="utf-8",
    )


def add_dbt_profile_downstream_model(*, sqlbuild_project_dir: Path) -> None:
    """Add a SQLBuild model downstream of the dbt profile E2E model."""

    models_dir: Path = sqlbuild_project_dir / "models"
    models_dir.mkdir(exist_ok=True)
    (models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id FROM __dbt_ref("analytics", "dbt_orders")\n',
        encoding="utf-8",
    )


def assert_dbt_profile_lifecycle(
    *,
    tmp_path: Path,
    profiles_yml: str,
    env: Mapping[str, str] | None,
    fetch_rows: Callable[[str], tuple[tuple[object, ...], ...]],
    no_profile_tables_exist: Callable[[], bool],
    dbt_orders_sql: str,
    downstream_orders_sql: str,
    expected_toml_fragments: tuple[str, ...],
    unexpected_toml_fragments: tuple[str, ...] = (),
) -> None:
    """Assert the common dbt-profile init/build lifecycle against a real warehouse."""

    workspace: Path = prepare_dbt_profile_workspace(
        tmp_path=tmp_path,
        profiles_yml=profiles_yml,
    )
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "dbt",
            "init",
            "--project-dir",
            "dbt_project",
            "--profiles-dir",
            "profiles",
            "--skip-dbt-debug",
        ),
        project_dir=workspace,
        env=env,
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr
    generated_toml: str = (sqlbuild_project_dir / "sqlbuild_project.toml").read_text(
        encoding="utf-8"
    )
    for fragment in expected_toml_fragments:
        assert fragment in generated_toml
    for fragment in unexpected_toml_fragments:
        assert fragment not in generated_toml

    add_dbt_profile_downstream_model(sqlbuild_project_dir=sqlbuild_project_dir)

    plain_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )
    assert plain_result.returncode != 0, plain_result.stdout + plain_result.stderr
    assert "Skipping dbt: no dbt work selected." in plain_result.stdout, (
        plain_result.stdout + plain_result.stderr
    )
    assert "depends on missing dbt relation(s)" in plain_result.stdout, (
        plain_result.stdout + plain_result.stderr
    )
    assert "Use --select +downstream_orders" in plain_result.stdout, (
        plain_result.stdout + plain_result.stderr
    )
    assert no_profile_tables_exist()

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )
    assert first_result.returncode == 0, first_result.stdout + first_result.stderr
    assert fetch_rows(dbt_orders_sql) == ((1,),)
    assert fetch_rows(downstream_orders_sql) == ((1,),)

    noop_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )
    assert noop_result.returncode == 0, noop_result.stdout + noop_result.stderr
    assert "Skipping dbt" in noop_result.stdout, noop_result.stdout + noop_result.stderr
    assert "Skipping SQLBuild" in noop_result.stdout, noop_result.stdout + noop_result.stderr

    write_dbt_profile_orders_model(workspace=workspace, order_id=2)
    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )
    assert changed_result.returncode == 0, changed_result.stdout + changed_result.stderr
    assert fetch_rows(dbt_orders_sql) == ((2,),)
    assert fetch_rows(downstream_orders_sql) == ((2,),)


def assert_dbt_complete_reuse_from_lifecycle(
    *,
    tmp_path: Path,
    profiles_yml: str,
    project_toml: str,
    fetch_rows: Callable[[str], tuple[tuple[object, ...], ...]],
    destination_rows_sql: str,
    downstream_rows_sql: str,
    expected_rows: tuple[tuple[object, ...], ...],
    env: Mapping[str, str] | None = None,
) -> None:
    """Assert dbt reuse_from complete table reuse against a real warehouse."""

    workspace: Path = tmp_path / "dbt_complete_reuse_from"
    dbt_project_dir: Path = workspace / "dbt_project"
    profiles_dir: Path = workspace / "profiles"
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    dbt_models_dir: Path = dbt_project_dir / "models"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    (profiles_dir / "profiles.yml").write_text(profiles_yml, encoding="utf-8")
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "fact_orders.sql").write_text(
        "select 1 as order_id, 900 as amount\n",
        encoding="utf-8",
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(project_toml, encoding="utf-8")
    (macro_dir / "prod_generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n"
        "  {{ target.schema.replace('_dev', '_prod') }}\n"
        "{%- endmacro %}\n",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id, amount AS downstream_amount FROM __dbt_ref("analytics", "fact_orders")\n',
        encoding="utf-8",
    )
    subprocess.run(("git", "init"), cwd=workspace, capture_output=True, check=True, text=True)
    subprocess.run(
        ("git", "config", "user.email", "sqlbuild@example.invalid"),
        cwd=workspace,
        capture_output=True,
        check=True,
        text=True,
    )
    subprocess.run(
        ("git", "config", "user.name", "SQLBuild Test"),
        cwd=workspace,
        capture_output=True,
        check=True,
        text=True,
    )
    subprocess.run(("git", "add", "."), cwd=workspace, capture_output=True, check=True, text=True)
    subprocess.run(
        ("git", "commit", "-m", "prod baseline"),
        cwd=workspace,
        capture_output=True,
        check=True,
        text=True,
    )
    subprocess.run(
        ("git", "branch", "prod"), cwd=workspace, capture_output=True, check=True, text=True
    )
    process_env: dict[str, str] = dict(os.environ)
    if env is not None:
        process_env.update(env)
    subprocess.run(
        (
            "dbt",
            "run",
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
            "--target",
            "prod",
        ),
        capture_output=True,
        check=True,
        env=process_env,
        text=True,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dbt reuse" in result.stdout
    assert "model.analytics.fact_orders" in result.stdout
    assert "OK     reuse" in result.stdout
    assert "dbt execution" not in result.stdout
    assert fetch_rows(destination_rows_sql) == expected_rows
    assert fetch_rows(downstream_rows_sql) == expected_rows

    rerun_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )

    assert rerun_result.returncode == 0, rerun_result.stdout + rerun_result.stderr
    assert "dbt reuse  pre-phase" not in rerun_result.stdout


def assert_dbt_seeded_reuse_from_lifecycle(
    *,
    tmp_path: Path,
    profiles_yml: str,
    project_toml: str,
    fetch_rows: Callable[[str], tuple[tuple[object, ...], ...]],
    execute_sql: Callable[[str], None],
    raw_orders_relation: str,
    destination_rows_sql: str,
    downstream_rows_sql: str,
    expected_rows: tuple[tuple[object, ...], ...],
    env: Mapping[str, str] | None = None,
    timestamp_type: str = "TIMESTAMP",
) -> None:
    """Assert dbt reuse_from seeded incremental reuse against a real warehouse."""

    workspace: Path = _prepare_dbt_reuse_workspace(
        tmp_path=tmp_path,
        workspace_name="dbt_seeded_reuse_from",
        profiles_yml=profiles_yml,
        project_toml=project_toml,
    )
    dbt_project_dir: Path = workspace / "dbt_project"
    profiles_dir: Path = workspace / "profiles"
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    _write_incremental_orders_model(
        dbt_models_dir=dbt_models_dir,
        raw_orders_relation=raw_orders_relation,
    )
    _seed_reuse_raw_orders(
        execute_sql=execute_sql,
        raw_orders_relation=raw_orders_relation,
        timestamp_type=timestamp_type,
    )
    _initialize_reuse_workspace_git(workspace=workspace)
    _run_reuse_workspace_dbt(
        command="run",
        dbt_project_dir=dbt_project_dir,
        profiles_dir=profiles_dir,
        target="prod",
        env=env,
    )
    _append_reuse_catchup_raw_orders(
        execute_sql=execute_sql,
        raw_orders_relation=raw_orders_relation,
        timestamp_type=timestamp_type,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dbt reuse" in result.stdout
    assert "model.analytics.fact_orders" in result.stdout
    assert "OK     baseline reuse before dbt catch-up" in result.stdout
    assert "dbt execution" in result.stdout
    assert fetch_rows(destination_rows_sql) == expected_rows
    assert fetch_rows(downstream_rows_sql) == expected_rows

    rerun_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )

    assert rerun_result.returncode == 0, rerun_result.stdout + rerun_result.stderr
    assert "dbt reuse  pre-phase" not in rerun_result.stdout


def assert_dbt_snapshot_seeded_reuse_from_lifecycle(
    *,
    tmp_path: Path,
    profiles_yml: str,
    project_toml: str,
    origin_snapshot_schema: str,
    destination_snapshot_schema: str,
    fetch_rows: Callable[[str], tuple[tuple[object, ...], ...]],
    execute_sql: Callable[[str], None],
    raw_orders_relation: str,
    destination_rows_sql: str,
    downstream_rows_sql: str,
    expected_rows: tuple[tuple[object, ...], ...],
    env: Mapping[str, str] | None = None,
    timestamp_type: str = "TIMESTAMP",
) -> None:
    """Assert dbt reuse_from seeded snapshot reuse against a real warehouse."""

    workspace: Path = _prepare_dbt_reuse_workspace(
        tmp_path=tmp_path,
        workspace_name="dbt_snapshot_seeded_reuse_from",
        profiles_yml=profiles_yml,
        project_toml=project_toml,
        include_snapshots=True,
        downstream_sql=(
            "SELECT order_id, amount AS downstream_amount "
            'FROM __dbt_ref("analytics", "orders_snapshot") WHERE dbt_valid_to IS NULL\n'
        ),
    )
    dbt_project_dir: Path = workspace / "dbt_project"
    profiles_dir: Path = workspace / "profiles"
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    snapshots_dir: Path = dbt_project_dir / "snapshots"
    _write_snapshot_orders_model(
        snapshots_dir=snapshots_dir,
        target_schema_expression=f"'{origin_snapshot_schema}'",
        raw_orders_relation=raw_orders_relation,
    )
    _seed_reuse_raw_orders(
        execute_sql=execute_sql,
        raw_orders_relation=raw_orders_relation,
        timestamp_type=timestamp_type,
    )
    _initialize_reuse_workspace_git(workspace=workspace)
    _run_reuse_workspace_dbt(
        command="snapshot",
        dbt_project_dir=dbt_project_dir,
        profiles_dir=profiles_dir,
        target="prod",
        env=env,
    )
    _write_snapshot_orders_model(
        snapshots_dir=snapshots_dir,
        target_schema_expression=f"'{destination_snapshot_schema}'",
        raw_orders_relation=raw_orders_relation,
    )
    _append_reuse_catchup_raw_orders(
        execute_sql=execute_sql,
        raw_orders_relation=raw_orders_relation,
        timestamp_type=timestamp_type,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dbt reuse" in result.stdout
    assert "snapshot.analytics.orders_snapshot" in result.stdout
    assert "OK     baseline reuse before dbt catch-up" in result.stdout
    assert "dbt execution" in result.stdout
    assert fetch_rows(destination_rows_sql) == expected_rows
    assert fetch_rows(downstream_rows_sql) == expected_rows

    rerun_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "downstream_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )

    assert rerun_result.returncode == 0, rerun_result.stdout + rerun_result.stderr
    assert "dbt reuse  pre-phase" not in rerun_result.stdout


def _prepare_dbt_reuse_workspace(
    *,
    tmp_path: Path,
    workspace_name: str,
    profiles_yml: str,
    project_toml: str,
    include_snapshots: bool = False,
    downstream_sql: str | None = None,
) -> Path:
    workspace: Path = tmp_path / workspace_name
    dbt_project_dir: Path = workspace / "dbt_project"
    profiles_dir: Path = workspace / "profiles"
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    (dbt_project_dir / "models").mkdir(parents=True)
    if include_snapshots:
        (dbt_project_dir / "snapshots").mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    (sqlbuild_project_dir / "models").mkdir(parents=True)
    (profiles_dir / "profiles.yml").write_text(profiles_yml, encoding="utf-8")
    snapshot_paths_line: str = "snapshot-paths: ['snapshots']\n" if include_snapshots else ""
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        f"{snapshot_paths_line}"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(project_toml, encoding="utf-8")
    (macro_dir / "prod_generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n"
        "  {{ target.schema.replace('_dev', '_prod') }}\n"
        "{%- endmacro %}\n",
        encoding="utf-8",
    )
    (sqlbuild_project_dir / "models" / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        + (
            downstream_sql
            or "SELECT order_id, amount AS downstream_amount "
            'FROM __dbt_ref("analytics", "fact_orders")\n'
        ),
        encoding="utf-8",
    )
    return workspace


def _seed_reuse_raw_orders(
    *,
    execute_sql: Callable[[str], None],
    raw_orders_relation: str,
    timestamp_type: str,
) -> None:
    execute_sql(f"DROP TABLE IF EXISTS {raw_orders_relation}")
    execute_sql(
        f"CREATE TABLE {raw_orders_relation} AS "
        "SELECT 1 AS order_id, 900 AS amount, "
        f"CAST('2026-01-01 00:00:00' AS {timestamp_type}) AS event_time"
    )


def _append_reuse_catchup_raw_orders(
    *,
    execute_sql: Callable[[str], None],
    raw_orders_relation: str,
    timestamp_type: str,
) -> None:
    execute_sql(
        f"INSERT INTO {raw_orders_relation} "
        "SELECT 2 AS order_id, 901 AS amount, "
        f"CAST('2026-01-02 00:00:00' AS {timestamp_type}) AS event_time"
    )


def _write_incremental_orders_model(*, dbt_models_dir: Path, raw_orders_relation: str) -> None:
    (dbt_models_dir / "fact_orders.sql").write_text(
        "{{ config(materialized='incremental', "
        "meta={'sqlbuild': {'reuse_cursor': 'event_time'}}) }}\n"
        f"SELECT order_id, amount, event_time FROM {raw_orders_relation}\n"
        "{% if is_incremental() %}\n"
        "WHERE event_time > (SELECT MAX(event_time) FROM {{ this }})\n"
        "{% endif %}\n",
        encoding="utf-8",
    )


def _write_snapshot_orders_model(
    *,
    snapshots_dir: Path,
    target_schema_expression: str,
    raw_orders_relation: str,
) -> None:
    (snapshots_dir / "orders_snapshot.sql").write_text(
        "{% snapshot orders_snapshot %}\n"
        "{{ config(\n"
        f"  target_schema={target_schema_expression},\n"
        "  unique_key='order_id',\n"
        "  strategy='timestamp',\n"
        "  updated_at='event_time',\n"
        "  meta={'sqlbuild': {'reuse_cursor': 'event_time'}}\n"
        ") }}\n"
        f"SELECT order_id, amount, event_time FROM {raw_orders_relation}\n"
        "{% endsnapshot %}\n",
        encoding="utf-8",
    )


def _initialize_reuse_workspace_git(*, workspace: Path) -> None:
    subprocess.run(("git", "init"), cwd=workspace, capture_output=True, check=True, text=True)
    subprocess.run(
        ("git", "config", "user.email", "sqlbuild@example.invalid"),
        cwd=workspace,
        capture_output=True,
        check=True,
        text=True,
    )
    subprocess.run(
        ("git", "config", "user.name", "SQLBuild Test"),
        cwd=workspace,
        capture_output=True,
        check=True,
        text=True,
    )
    subprocess.run(("git", "add", "."), cwd=workspace, capture_output=True, check=True, text=True)
    subprocess.run(
        ("git", "commit", "-m", "prod baseline"),
        cwd=workspace,
        capture_output=True,
        check=True,
        text=True,
    )
    subprocess.run(
        ("git", "branch", "prod"), cwd=workspace, capture_output=True, check=True, text=True
    )


def _run_reuse_workspace_dbt(
    *,
    command: str,
    dbt_project_dir: Path,
    profiles_dir: Path,
    target: str,
    env: Mapping[str, str] | None,
) -> None:
    process_env: dict[str, str] = dict(os.environ)
    if env is not None:
        process_env.update(env)
    subprocess.run(
        (
            "dbt",
            command,
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
            "--target",
            target,
        ),
        capture_output=True,
        check=True,
        env=process_env,
        text=True,
    )


def run_sqb(
    *,
    command: tuple[str, ...],
    project_dir: Path,
    env: Mapping[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an sqb CLI command via subprocess and return the result."""

    process_env: dict[str, str] = dict(os.environ)
    if env is not None:
        process_env.update(env)

    return subprocess.run(
        ["uv", "run", "sqb", "--project-dir", str(project_dir), *command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        input=input_text,
        env=process_env,
        check=False,
    )


def query_duckdb(*, db_path: Path, sql: str) -> list[tuple[Any, ...]]:
    """Open a DuckDB file and execute a query, returning all rows."""

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path), read_only=True)
    try:
        result: list[tuple[Any, ...]] = connection.execute(sql).fetchall()
    finally:
        connection.close()
    return result


def execute_duckdb(*, db_path: Path, sql: str) -> None:
    """Open a DuckDB file and execute a mutating statement."""

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    try:
        connection.execute(sql)
    finally:
        connection.close()


def table_exists(*, db_path: Path, table_name: str, schema: str = "main") -> bool:
    """Check if a table or view exists in the DuckDB file."""

    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            f"SELECT 1 FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' AND table_name = '{table_name}'"
        ),
    )
    return len(rows) > 0


def row_count(*, db_path: Path, table_name: str, schema: str = "main") -> int:
    """Count rows in a table in the DuckDB file."""

    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=f"SELECT COUNT(*) FROM {schema}.{table_name}",
    )
    return int(rows[0][0])


def normalize_cli_output(output: str) -> str:
    """Normalize dynamic CLI output fragments for stable assertions."""

    normalized: str = re.sub(r"\(\d+\.\d{2}s\)", "(<time>)", output)
    normalized = re.sub(
        r"PASS=\d+  WARN=\d+  FAIL=\d+  SKIP=\d+  TOTAL=\d+  \(<time>\)",
        "PASS=<n>  WARN=<n>  FAIL=<n>  SKIP=<n>  TOTAL=<n>  (<time>)",
        normalized,
    )
    normalized = re.sub(
        r"PASS=\d+  WARN=\d+  FAIL=\d+  TOTAL=\d+",
        "PASS=<n>  WARN=<n>  FAIL=<n>  TOTAL=<n>",
        normalized,
    )
    normalized = re.sub(
        r"PASS=\d+  FAIL=\d+  TOTAL=\d+", "PASS=<n>  FAIL=<n>  TOTAL=<n>", normalized
    )
    return normalized


def assert_fragments_in_order(output: str, fragments: tuple[str, ...]) -> None:
    """Assert that fragments appear in order within normalized output."""

    normalized_output: str = normalize_cli_output(output)
    position: int = 0
    fragment: str
    for fragment in fragments:
        index: int = normalized_output.find(fragment, position)
        assert index != -1, f"missing fragment in order: {fragment!r}\n\n{normalized_output}"
        position = index + len(fragment)


def assert_snapshot_scd2_invariants(
    *,
    db_path: Path,
    table_name: str,
    key_columns: tuple[str, ...],
    valid_from_column: str = "valid_from",
    valid_to_column: str = "valid_to",
    schema: str = "main",
) -> None:
    """Assert generic SCD2 safety invariants for a snapshot table."""

    key_sql: str = ", ".join(key_columns)
    key_match_sql: str = " AND ".join(
        f"left_row.{column} = right_row.{column}" for column in key_columns
    )
    tie_break_sql: str = " OR ".join(
        f"left_row.{column} <> right_row.{column}" for column in (*key_columns, valid_to_column)
    )
    qualified_table: str = f"{schema}.{table_name}"

    duplicate_open_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT COUNT(*) FROM ("
            f"SELECT {key_sql} FROM {qualified_table} WHERE {valid_to_column} IS NULL "
            f"GROUP BY {key_sql} HAVING COUNT(*) > 1"
            ")"
        ),
    )
    duplicate_valid_from_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT COUNT(*) FROM ("
            f"SELECT {key_sql}, {valid_from_column} FROM {qualified_table} "
            f"GROUP BY {key_sql}, {valid_from_column} HAVING COUNT(*) > 1"
            ")"
        ),
    )
    invalid_interval_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            f"SELECT COUNT(*) FROM {qualified_table} "
            f"WHERE {valid_to_column} IS NOT NULL "
            f"AND {valid_from_column} >= {valid_to_column}"
        ),
    )
    overlapping_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT COUNT(*) FROM ("
            f"SELECT 1 FROM {qualified_table} AS left_row "
            f"JOIN {qualified_table} AS right_row ON {key_match_sql} "
            f"AND ({tie_break_sql}) "
            f"AND left_row.{valid_from_column} < "
            f"COALESCE(right_row.{valid_to_column}, TIMESTAMP '9999-12-31') "
            f"AND right_row.{valid_from_column} < "
            f"COALESCE(left_row.{valid_to_column}, TIMESTAMP '9999-12-31')"
            ")"
        ),
    )

    assert duplicate_open_rows == [(0,)]
    assert duplicate_valid_from_rows == [(0,)]
    assert invalid_interval_rows == [(0,)]
    assert overlapping_rows == [(0,)]


def build_real_warehouse_snapshot_project_files(*, project_toml: str) -> dict[str, str]:
    """Build a compact real-warehouse project covering snapshot execution paths."""

    return {
        "sqlbuild_project.toml": project_toml,
        "models/current_customers.sql": build_current_customers_model_sql(plan="basic"),
        "models/current_customer_snapshot.sql": (
            "MODEL (\n"
            "  materialized snapshot,\n"
            "  unique_key [customer_id, region_id],\n"
            "  snapshot_strategy timestamp,\n"
            "  updated_at updated_at,\n"
            "  valid_from_column effective_from,\n"
            "  valid_to_column effective_to,\n"
            "  audits [\n"
            "    expression_is_true (\n"
            '      name "plan is allowed",\n'
            "      expression \"plan <> 'blocked'\",\n"
            "    ),\n"
            "  ],\n"
            ");\n\n"
            "SELECT customer_id, region_id, plan, updated_at\n"
            'FROM __ref("current_customers")\n'
        ),
        "models/historical_customer_extracts.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "CAST('2026-01-01 00:00:00' AS TIMESTAMP) AS updated_at, "
            "CAST('2026-01-02 00:00:00' AS TIMESTAMP) AS observed_at\n"
            "UNION ALL SELECT 1 AS customer_id, 'pro' AS plan, "
            "CAST('2026-01-03 00:00:00' AS TIMESTAMP) AS updated_at, "
            "CAST('2026-01-04 00:00:00' AS TIMESTAMP) AS observed_at\n"
            "UNION ALL SELECT 2 AS customer_id, 'trial' AS plan, "
            "CAST('2026-01-02 00:00:00' AS TIMESTAMP) AS updated_at, "
            "CAST('2026-01-04 00:00:00' AS TIMESTAMP) AS observed_at\n"
        ),
        "models/historical_customer_snapshot.sql": (
            "MODEL (\n"
            "  materialized snapshot,\n"
            "  unique_key [customer_id],\n"
            "  snapshot_strategy timestamp,\n"
            "  updated_at updated_at,\n"
            "  observed_at observed_at,\n"
            "  historical_input snapshot\n"
            ");\n\n"
            "SELECT customer_id, plan, updated_at, observed_at\n"
            'FROM __ref("historical_customer_extracts")\n'
        ),
        "models/historical_membership_daily.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT 1 AS customer_id, 'active' AS status, "
            "CAST('2026-01-01 00:00:00' AS TIMESTAMP) AS observed_at\n"
            "UNION ALL SELECT 2 AS customer_id, 'active' AS status, "
            "CAST('2026-01-01 00:00:00' AS TIMESTAMP) AS observed_at\n"
            "UNION ALL SELECT 1 AS customer_id, 'active' AS status, "
            "CAST('2026-01-02 00:00:00' AS TIMESTAMP) AS observed_at\n"
            "UNION ALL SELECT 1 AS customer_id, 'paused' AS status, "
            "CAST('2026-01-03 00:00:00' AS TIMESTAMP) AS observed_at\n"
            "UNION ALL SELECT 2 AS customer_id, 'active' AS status, "
            "CAST('2026-01-03 00:00:00' AS TIMESTAMP) AS observed_at\n"
        ),
        "models/historical_membership_snapshot.sql": (
            "MODEL (\n"
            "  materialized snapshot,\n"
            "  unique_key [customer_id],\n"
            "  snapshot_strategy check,\n"
            "  check_columns [status],\n"
            "  observed_at observed_at,\n"
            "  historical_input snapshot,\n"
            "  invalidate_hard_deletes true\n"
            ");\n\n"
            "SELECT customer_id, status, observed_at\n"
            'FROM __ref("historical_membership_daily")\n'
        ),
        "audits/generic/expression_is_true.sql": (
            'AUDIT ();\n\nSELECT * FROM __ref("@model") WHERE NOT (@expression)\n'
        ),
    }


def build_current_customers_model_sql(*, plan: str, updated_at: str = "2026-01-01 00:00:00") -> str:
    """Build the mutable current-state model for real-warehouse snapshot tests."""

    return (
        "MODEL (materialized table);\n\n"
        "SELECT 1 AS customer_id, 10 AS region_id, "
        f"'{plan}' AS plan, CAST('{updated_at}' AS TIMESTAMP) AS updated_at\n"
    )


def build_real_warehouse_existing_snapshot_project_files(*, project_toml: str) -> dict[str, str]:
    """Build a live project that forces existing-target snapshot DML paths."""

    return {
        "sqlbuild_project.toml": project_toml,
        "models/current_check_customers.sql": build_current_check_customers_model_sql(
            changed=False
        ),
        "models/current_check_snapshot.sql": (
            "MODEL (\n"
            "  materialized snapshot,\n"
            "  unique_key [customer_id],\n"
            "  snapshot_strategy check,\n"
            "  check_columns [*]\n"
            ");\n\n"
            "SELECT customer_id, status\n"
            'FROM __ref("current_check_customers")\n'
        ),
        "models/current_delete_customers.sql": build_current_delete_customers_model_sql(
            changed=False
        ),
        "models/current_delete_snapshot.sql": (
            "MODEL (\n"
            "  materialized snapshot,\n"
            "  unique_key [customer_id],\n"
            "  snapshot_strategy timestamp,\n"
            "  updated_at updated_at,\n"
            "  invalidate_hard_deletes true\n"
            ");\n\n"
            "SELECT customer_id, plan, updated_at\n"
            'FROM __ref("current_delete_customers")\n'
        ),
        "models/historical_timestamp_extracts.sql": build_historical_timestamp_extracts_model_sql(
            changed=False
        ),
        "models/historical_timestamp_snapshot.sql": (
            "MODEL (\n"
            "  materialized snapshot,\n"
            "  unique_key [customer_id],\n"
            "  snapshot_strategy timestamp,\n"
            "  updated_at updated_at,\n"
            "  observed_at observed_at,\n"
            "  historical_input snapshot,\n"
            "  invalidate_hard_deletes true\n"
            ");\n\n"
            "SELECT customer_id, plan, updated_at, observed_at\n"
            'FROM __ref("historical_timestamp_extracts")\n'
        ),
        "models/historical_check_daily.sql": build_historical_check_daily_model_sql(changed=False),
        "models/historical_check_snapshot.sql": (
            "MODEL (\n"
            "  materialized snapshot,\n"
            "  unique_key [customer_id],\n"
            "  snapshot_strategy check,\n"
            "  check_columns [*],\n"
            "  observed_at observed_at,\n"
            "  historical_input snapshot,\n"
            "  invalidate_hard_deletes true\n"
            ");\n\n"
            "SELECT customer_id, status, observed_at\n"
            'FROM __ref("historical_check_daily")\n'
        ),
    }


def build_current_check_customers_model_sql(*, changed: bool) -> str:
    """Build mutable current-check source model for live snapshot apply tests."""

    if changed:
        return (
            "MODEL (materialized table);\n\n"
            "SELECT 1 AS customer_id, 'paused' AS status\n"
            "UNION ALL SELECT 2 AS customer_id, 'active' AS status\n"
        )
    return (
        "MODEL (materialized table);\n\n"
        "SELECT 1 AS customer_id, 'active' AS status\n"
        "UNION ALL SELECT 2 AS customer_id, 'active' AS status\n"
    )


def build_current_delete_customers_model_sql(*, changed: bool) -> str:
    """Build mutable current timestamp source model for hard-delete apply tests."""

    if changed:
        return (
            "MODEL (materialized table);\n\n"
            "SELECT 1 AS customer_id, 'pro' AS plan, "
            "CAST('2026-01-03 00:00:00' AS TIMESTAMP) AS updated_at\n"
        )
    return (
        "MODEL (materialized table);\n\n"
        "SELECT 1 AS customer_id, 'basic' AS plan, "
        "CAST('2026-01-01 00:00:00' AS TIMESTAMP) AS updated_at\n"
        "UNION ALL SELECT 2 AS customer_id, 'trial' AS plan, "
        "CAST('2026-01-01 00:00:00' AS TIMESTAMP) AS updated_at\n"
    )


def build_historical_timestamp_extracts_model_sql(*, changed: bool) -> str:
    """Build mutable historical timestamp source model for live apply tests."""

    sql: str = (
        "MODEL (materialized table);\n\n"
        "SELECT 1 AS customer_id, 'basic' AS plan, "
        "CAST('2026-01-01 00:00:00' AS TIMESTAMP) AS updated_at, "
        "CAST('2026-01-02 00:00:00' AS TIMESTAMP) AS observed_at\n"
        "UNION ALL SELECT 2 AS customer_id, 'trial' AS plan, "
        "CAST('2026-01-01 00:00:00' AS TIMESTAMP) AS updated_at, "
        "CAST('2026-01-02 00:00:00' AS TIMESTAMP) AS observed_at\n"
    )
    if changed:
        sql += (
            "UNION ALL SELECT 1 AS customer_id, 'pro' AS plan, "
            "CAST('2026-01-03 00:00:00' AS TIMESTAMP) AS updated_at, "
            "CAST('2026-01-04 00:00:00' AS TIMESTAMP) AS observed_at\n"
        )
    return sql


def build_historical_check_daily_model_sql(*, changed: bool) -> str:
    """Build mutable historical check source model for live apply tests."""

    sql: str = (
        "MODEL (materialized table);\n\n"
        "SELECT 1 AS customer_id, 'active' AS status, "
        "CAST('2026-01-01 00:00:00' AS TIMESTAMP) AS observed_at\n"
        "UNION ALL SELECT 2 AS customer_id, 'active' AS status, "
        "CAST('2026-01-01 00:00:00' AS TIMESTAMP) AS observed_at\n"
        "UNION ALL SELECT 1 AS customer_id, 'active' AS status, "
        "CAST('2026-01-02 00:00:00' AS TIMESTAMP) AS observed_at\n"
    )
    if changed:
        sql += (
            "UNION ALL SELECT 1 AS customer_id, 'paused' AS status, "
            "CAST('2026-01-03 00:00:00' AS TIMESTAMP) AS observed_at\n"
            "UNION ALL SELECT 2 AS customer_id, 'active' AS status, "
            "CAST('2026-01-03 00:00:00' AS TIMESTAMP) AS observed_at\n"
        )
    return sql


def stringify_warehouse_rows(
    rows: tuple[tuple[object, ...], ...],
) -> tuple[tuple[object, ...], ...]:
    """Normalize warehouse driver scalar differences for stable e2e assertions."""

    return tuple(tuple(None if value is None else str(value) for value in row) for row in rows)
