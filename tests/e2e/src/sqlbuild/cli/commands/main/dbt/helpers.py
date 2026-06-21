from __future__ import annotations

import json
import os
import pty
import select
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from shutil import copytree
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtLineageErrorE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import REPO_ROOT, execute_duckdb

DBT_INTEROP_FIXTURE_DIR: Path = REPO_ROOT / "tests" / "e2e" / "fixtures" / "dbt_interop"


def dbt_executable() -> str:
    """Return the dbt executable for e2e tests, honoring DBT_EXECUTABLE."""

    override: str | None = os.environ.get("DBT_EXECUTABLE")
    if override is not None and override.strip():
        return override.strip()
    return "dbt"


def skip_unless_dbt_is_runnable() -> None:
    """Skip e2e dbt tests when the dbt CLI is unavailable."""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        (dbt_executable(), "--version"),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"dbt CLI is not runnable: {result.stderr or result.stdout}")


def prepare_dbt_init_duckdb_workspace(*, tmp_path: Path, workspace_name: str) -> Path:
    """Write a minimal dbt project and profile for dbt init E2Es."""

    workspace: Path = tmp_path / workspace_name
    dbt_project_dir: Path = workspace / "dbt_project"
    profiles_dir: Path = workspace / "profiles"
    dbt_models_dir: Path = dbt_project_dir / "models"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    db_path: Path = workspace / "warehouse.duckdb"
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
    write_dbt_init_orders_model(workspace=workspace, amount_cents=900)
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: main\n"
        "    prod:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: prod\n",
        encoding="utf-8",
    )
    return workspace


def write_dbt_init_orders_model(*, workspace: Path, amount_cents: int) -> None:
    """Write the mutable dbt model used by dbt init E2Es."""

    workspace.joinpath("dbt_project", "models", "dbt_orders.sql").write_text(
        f"select 1 as order_id, {amount_cents} as amount_cents\n",
        encoding="utf-8",
    )


def initialize_dbt_init_git_repo(*, workspace: Path, production_ref: str) -> None:
    """Create a production ref and feature branch for generated reuse config E2Es."""

    _run_git(args=("init",), cwd=workspace)
    _run_git(args=("config", "user.email", "sqlbuild@example.invalid"), cwd=workspace)
    _run_git(args=("config", "user.name", "SQLBuild Test"), cwd=workspace)
    _run_git(args=("add", "."), cwd=workspace)
    _run_git(args=("commit", "-m", "prod baseline"), cwd=workspace)
    _run_git(args=("branch", production_ref), cwd=workspace)
    _run_git(args=("checkout", "-b", "feature"), cwd=workspace)


def prepare_dbt_diff_workspace(
    *,
    tmp_path: Path,
    workspace_name: str,
    include_unique_key: bool = True,
    include_cursor_meta: bool = True,
    include_reuse_from: bool = True,
    reuse_git_ref: str = "prod",
    include_second_model: bool = False,
    include_view_model: bool = False,
) -> Path:
    """Build a dbt diff workspace with prod and feature branch order tables."""

    workspace: Path = tmp_path / workspace_name
    dbt_project_dir: Path = workspace / "dbt_project"
    profiles_dir: Path = workspace / "profiles"
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    (dbt_project_dir / "models").mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = workspace / "warehouse.duckdb"
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
    write_dbt_diff_orders_model(
        workspace=workspace,
        amount_cents=900,
        order_ids=(1, 2),
        include_unique_key=include_unique_key,
        include_cursor_meta=include_cursor_meta,
    )
    if include_second_model:
        _write_dbt_diff_customers_model(workspace=workspace)
    if include_view_model:
        write_dbt_clone_summary_view_model(workspace=workspace, amount_cents=900)
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: main\n"
        "    prod:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: prod\n",
        encoding="utf-8",
    )
    reuse_block: str = (
        "\n[dbt.reuse_from]\n"
        f'git_ref = "{reuse_git_ref}"\n'
        'generate_schema_name_override = "dbt/macros/generate_schema_name.sql"\n'
        if include_reuse_from
        else ""
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(
        'name = "analytics_sqb"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        'source = "dbt_profile"\n'
        'profile = "analytics"\n\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n'
        f"{reuse_block}\n"
        "[targets.dev.connection]\n"
        'source = "dbt_profile"\n'
        'profile = "analytics"\n'
        'target = "dev"\n',
        encoding="utf-8",
    )
    macro_dir.joinpath("generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n  prod\n{%- endmacro %}\n",
        encoding="utf-8",
    )
    _initialize_dbt_diff_git(workspace=workspace)
    _run_dbt(
        args=("run",),
        dbt_project_dir=dbt_project_dir,
        profiles_dir=profiles_dir,
        target="prod",
    )
    _run_git(args=("checkout", "-b", "feature"), cwd=workspace)
    return workspace


def _write_dbt_diff_customers_model(*, workspace: Path) -> None:
    workspace.joinpath("dbt_project", "models", "dbt_customers.sql").write_text(
        "{{ config(\n"
        "    materialized='table',\n"
        "    unique_key='customer_id',\n"
        "    tags=['finance']\n"
        ") }}\n\n"
        "select 1 as customer_id, 'alice' as name\n",
        encoding="utf-8",
    )


def write_dbt_clone_summary_view_model(*, workspace: Path, amount_cents: int) -> None:
    """Write the mutable dbt view model used by clone E2Es."""

    workspace.joinpath("dbt_project", "models", "dbt_order_summary.sql").write_text(
        f"{{{{ config(materialized='view') }}}}\n\nselect {amount_cents} as total_amount_cents\n",
        encoding="utf-8",
    )


def drop_dbt_clone_origin_orders_relation(*, workspace: Path) -> None:
    """Drop the prod relation after manifest baseline creation for warning E2Es."""

    execute_duckdb(
        db_path=workspace / "warehouse.duckdb",
        sql="DROP TABLE IF EXISTS prod.dbt_orders",
    )


def write_dbt_diff_orders_model(
    *,
    workspace: Path,
    amount_cents: int,
    order_ids: tuple[int, ...],
    include_unique_key: bool,
    include_cursor_meta: bool,
) -> None:
    """Write the dbt orders model used by diff E2Es."""

    config_lines: list[str] = ["    materialized='table'"]
    if include_unique_key:
        config_lines.append("    unique_key='order_id'")
    if include_cursor_meta:
        config_lines.append(
            "    meta={'sqlbuild': {'cursor': 'updated_at', 'cursor_type': 'timestamp'}}"
        )
    config_block: str = "{{ config(\n" + ",\n".join(config_lines) + "\n) }}\n"
    selects: tuple[str, ...] = tuple(
        f"select {order_id} as order_id, {amount_cents} as amount_cents, "
        f"cast('2026-06-17 0{index}:00:00' as timestamp) as updated_at"
        for index, order_id in enumerate(order_ids)
    )
    workspace.joinpath("dbt_project", "models", "dbt_orders.sql").write_text(
        config_block + "\n" + "\nunion all\n".join(selects) + "\n",
        encoding="utf-8",
    )


def build_dbt_diff_current_model(*, workspace: Path) -> None:
    """Build the current dbt model into the dev schema with dbt directly."""

    _run_dbt(
        args=("run",),
        dbt_project_dir=workspace / "dbt_project",
        profiles_dir=workspace / "profiles",
        target="dev",
    )


def _initialize_dbt_diff_git(*, workspace: Path) -> None:
    _run_git(args=("init",), cwd=workspace)
    _run_git(args=("config", "user.email", "sqlbuild@example.invalid"), cwd=workspace)
    _run_git(args=("config", "user.name", "SQLBuild Test"), cwd=workspace)
    _run_git(args=("add", "."), cwd=workspace)
    _run_git(args=("commit", "-m", "prod baseline"), cwd=workspace)
    _run_git(args=("branch", "prod"), cwd=workspace)


def run_sqb_with_pty(
    *, command: tuple[str, ...], project_dir: Path, input_text: str, timeout_seconds: float = 60.0
) -> subprocess.CompletedProcess[str]:
    """Run sqb through a real PTY and return captured terminal output."""

    master_fd: int
    slave_fd: int
    master_fd, slave_fd = pty.openpty()
    process_env: dict[str, str] = dict(os.environ)
    process_env["TERM"] = "xterm-256color"
    process: subprocess.Popen[bytes] = subprocess.Popen(
        ["uv", "run", "sqb", "--project-dir", str(project_dir), *command],
        cwd=REPO_ROOT,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=process_env,
        close_fds=True,
    )
    os.close(slave_fd)
    output_parts: list[bytes] = []
    input_written: bool = False
    deadline: float = time.monotonic() + timeout_seconds
    try:
        while process.poll() is None:
            if time.monotonic() > deadline:
                process.kill()
                raise subprocess.TimeoutExpired(command, timeout_seconds)
            readable: list[int]
            readable, _, _ = select.select([master_fd], [], [], 0.05)
            if readable:
                try:
                    output_parts.append(os.read(master_fd, 4096))
                except OSError:
                    break
            if not input_written:
                os.write(master_fd, input_text.encode())
                input_written = True
        while True:
            readable, _, _ = select.select([master_fd], [], [], 0)
            if not readable:
                break
            try:
                output_parts.append(os.read(master_fd, 4096))
            except OSError:
                break
    finally:
        os.close(master_fd)
    output: str = b"".join(output_parts).decode(errors="replace")
    return subprocess.CompletedProcess(
        args=("sqb", *command), returncode=process.returncode or 0, stdout=output, stderr=""
    )


def prepare_dbt_interop_project(*, tmp_path: Path) -> Path:
    """Copy the reusable dbt interop fixture and return its SQLBuild project root."""

    root_dir: Path = tmp_path / "dbt_interop"
    copytree(DBT_INTEROP_FIXTURE_DIR, root_dir)
    local_config_path: Path = root_dir / "sqlbuild_project" / "sqlbuild_local.toml"
    if local_config_path.exists():
        local_config_path.unlink()
    db_path: Path = root_dir / "sqlbuild_project" / "dbt_interop.duckdb"
    if db_path.exists():
        db_path.unlink()
    profiles_path: Path = root_dir / "profiles" / "profiles.yml"
    profiles_path.write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n",
        encoding="utf-8",
    )
    return root_dir / "sqlbuild_project"


def write_dbt_model_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write a SQLBuild unit test that targets a dbt model directly."""

    project_dir.joinpath("tests", "unit", "test_dbt_fact_orders.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__dbt_ref__stg_orders AS (\n"
        "  SELECT 10 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__fact_orders AS (\n"
        "  SELECT 10 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_qualified_dbt_model_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write a SQLBuild unit test with a package-qualified dbt expected target."""

    project_dir.joinpath("tests", "unit", "test_dbt_fact_orders.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__dbt_ref__stg_orders AS (\n"
        "  SELECT 10 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__analytics__fact_orders AS (\n"
        "  SELECT 10 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_incremental_dbt_model_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write an incremental dbt model and unit test that require full-refresh compile."""

    project_dir.parent.joinpath("dbt_project", "models", "marts", "fact_orders.sql").write_text(
        "{{ config(materialized='incremental', unique_key='order_id', tags=['finance']) }}\n\n"
        "select order_id, ordered_at, 'full' as branch from {{ ref('stg_orders') }}\n"
        "{% if is_incremental() %}\n"
        "union all select 999 as order_id, cast('2026-01-01 00:00:00' as timestamp) "
        "as ordered_at, 'incremental' as branch\n"
        "{% endif %}\n",
        encoding="utf-8",
    )
    project_dir.joinpath("tests", "unit", "test_dbt_fact_orders.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__dbt_ref__stg_orders AS (\n"
        "  SELECT 10 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__fact_orders AS (\n"
        "  SELECT 10 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at, "
        "'full' AS branch\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_dbt_source_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write a dbt source-backed model and SQLBuild unit test targeting it."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    dbt_project_dir.joinpath("models", "staging", "stg_orders_from_source.sql").write_text(
        "select order_id, ordered_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    schema_path: Path = dbt_project_dir / "models" / "schema.yml"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8")
        + "\nsources:\n"
        + "  - name: raw\n"
        + "    schema: raw\n"
        + "    tables:\n"
        + "      - name: orders\n",
        encoding="utf-8",
    )
    project_dir.joinpath("tests", "unit", "test_dbt_stg_orders_from_source.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__source__raw__orders AS (\n"
        "  SELECT 20 AS order_id, cast('2026-02-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__stg_orders_from_source AS (\n"
        "  SELECT 20 AS order_id, cast('2026-02-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_dbt_seed_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write a dbt seed-backed model and SQLBuild unit test targeting it."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    seeds_dir: Path = dbt_project_dir / "seeds"
    seeds_dir.mkdir()
    seeds_dir.joinpath("countries.csv").write_text(
        "country_code,country_name\nUS,United States\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "marts", "dim_countries.sql").write_text(
        "select country_code, country_name from {{ ref('countries') }}\n",
        encoding="utf-8",
    )
    project_dir.joinpath("tests", "unit", "test_dbt_dim_countries.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__seed__countries AS (\n"
        "  SELECT 'CA' AS country_code, 'Canada' AS country_name\n"
        "),\n"
        "__expected__dim_countries AS (\n"
        "  SELECT 'CA' AS country_code, 'Canada' AS country_name\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_chained_dbt_source_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write a two-model dbt source chain and SQLBuild unit test targeting the final model."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    dbt_project_dir.joinpath("models", "staging", "stg_orders_from_source.sql").write_text(
        "select order_id, ordered_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "marts", "fact_orders_from_source.sql").write_text(
        "select order_id, ordered_at from {{ ref('stg_orders_from_source') }}\n",
        encoding="utf-8",
    )
    schema_path: Path = dbt_project_dir / "models" / "schema.yml"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8")
        + "\nsources:\n"
        + "  - name: raw\n"
        + "    schema: raw\n"
        + "    tables:\n"
        + "      - name: orders\n",
        encoding="utf-8",
    )
    project_dir.joinpath("tests", "unit", "test_dbt_fact_orders_from_source.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__source__raw__orders AS (\n"
        "  SELECT 30 AS order_id, cast('2026-03-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__fact_orders_from_source AS (\n"
        "  SELECT 30 AS order_id, cast('2026-03-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_chained_dbt_seed_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write a two-model dbt seed chain and SQLBuild unit test targeting the final model."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    seeds_dir: Path = dbt_project_dir / "seeds"
    seeds_dir.mkdir()
    seeds_dir.joinpath("countries.csv").write_text(
        "country_code,country_name\nUS,United States\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "staging", "stg_countries.sql").write_text(
        "select country_code, country_name from {{ ref('countries') }}\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "marts", "dim_country_names.sql").write_text(
        "select country_code, country_name from {{ ref('stg_countries') }}\n",
        encoding="utf-8",
    )
    project_dir.joinpath("tests", "unit", "test_dbt_dim_country_names.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__seed__countries AS (\n"
        "  SELECT 'MX' AS country_code, 'Mexico' AS country_name\n"
        "),\n"
        "__expected__dim_country_names AS (\n"
        "  SELECT 'MX' AS country_code, 'Mexico' AS country_name\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_dbt_scenario_targeting_dbt_model(*, project_dir: Path) -> None:
    """Write a dbt source-backed model and a scenario targeting that dbt model."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    dbt_project_dir.joinpath("models", "staging", "stg_scenario_orders.sql").write_text(
        "select order_id, ordered_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    schema_path: Path = dbt_project_dir / "models" / "schema.yml"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8")
        + "\nsources:\n"
        + "  - name: raw\n"
        + "    schema: raw\n"
        + "    tables:\n"
        + "      - name: orders\n",
        encoding="utf-8",
    )
    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_stg_scenario_orders.sql").write_text(
        'SCENARIO (description: "dbt scenario target", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__source__raw__orders AS (\n"
        "  SELECT 60 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__stg_scenario_orders AS (\n"
        "  SELECT 60 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__assert__no_zero_orders AS (\n"
        '  SELECT * FROM __ref("stg_scenario_orders") WHERE order_id = 0\n'
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_chained_dbt_scenario_targeting_dbt_model(*, project_dir: Path) -> None:
    """Write a two-model dbt source chain and a scenario targeting the final dbt model."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    dbt_project_dir.joinpath("models", "staging", "stg_scenario_chain.sql").write_text(
        "select order_id, ordered_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "marts", "fact_scenario_chain.sql").write_text(
        "select order_id, ordered_at from {{ ref('stg_scenario_chain') }}\n",
        encoding="utf-8",
    )
    schema_path: Path = dbt_project_dir / "models" / "schema.yml"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8")
        + "\nsources:\n"
        + "  - name: raw\n"
        + "    schema: raw\n"
        + "    tables:\n"
        + "      - name: orders\n",
        encoding="utf-8",
    )
    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_fact_scenario_chain.sql").write_text(
        'SCENARIO (description: "chained dbt scenario target", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__source__raw__orders AS (\n"
        "  SELECT 70 AS order_id, cast('2026-07-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__fact_scenario_chain AS (\n"
        "  SELECT 70 AS order_id, cast('2026-07-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_spanning_sqlbuild_dbt_ref_scenario(*, project_dir: Path) -> None:
    """Write a scenario over a SQLBuild model whose chain crosses a dbt ref boundary.

    mart_orders -> downstream_orders (both SQLBuild) -> __dbt_ref(analytics, fact_orders).
    The dbt ref is mocked; downstream_orders resolves from its real SQL.
    """

    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("mart_orders_spanning.sql").write_text(
        'SCENARIO (description: "mixed dbt and SQLBuild graph scenario", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__dbt_ref__analytics__fact_orders AS (\n"
        "  SELECT 42 AS order_id\n"
        "),\n"
        "__expected__mart_orders AS (\n"
        "  SELECT 42 AS order_id\n"
        "),\n"
        "__assert__mart_orders_nonzero AS (\n"
        '  SELECT * FROM __ref("mart_orders") WHERE order_id = 0\n'
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_real_source_fixture_dbt_scenario(*, project_dir: Path) -> None:
    """Write a dbt source-backed model and a scenario whose fixture reads the real source."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    dbt_project_dir.joinpath("models", "staging", "stg_real_source_orders.sql").write_text(
        "select order_id, ordered_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    schema_path: Path = dbt_project_dir / "models" / "schema.yml"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8")
        + "\nsources:\n"
        + "  - name: raw\n"
        + "    schema: raw\n"
        + "    tables:\n"
        + "      - name: orders\n",
        encoding="utf-8",
    )
    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_real_source_fixture.sql").write_text(
        'SCENARIO (description: "fixture reads real dbt source", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__source__raw__orders AS (\n"
        '  SELECT order_id, ordered_at FROM __source("raw__orders") WHERE order_id = 1\n'
        "),\n"
        "__expected__stg_real_source_orders AS (\n"
        "  SELECT 1 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def seed_real_dbt_source_orders(*, project_dir: Path) -> None:
    """Create the physical raw.orders source table the dbt source points at."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    db_path: Path = project_dir / "dbt_interop.duckdb"
    execute_duckdb(db_path=db_path, sql="CREATE SCHEMA IF NOT EXISTS raw")
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE raw.orders AS "
            "SELECT 1 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at "
            "UNION ALL "
            "SELECT 2 AS order_id, cast('2026-02-02 00:00:00' as timestamp) AS ordered_at"
        ),
    )


def _write_dbt_source_orders_model(*, project_dir: Path, model_name: str) -> None:
    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    dbt_project_dir.joinpath("models", "staging", f"{model_name}.sql").write_text(
        "select order_id, ordered_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    schema_path: Path = dbt_project_dir / "models" / "schema.yml"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8")
        + "\nsources:\n"
        + "  - name: raw\n"
        + "    schema: raw\n"
        + "    tables:\n"
        + "      - name: orders\n",
        encoding="utf-8",
    )


def write_failing_assertion_dbt_scenario(*, project_dir: Path) -> None:
    """Write a dbt scenario whose zero-row assertion is violated."""

    _write_dbt_source_orders_model(project_dir=project_dir, model_name="stg_scenario_fail_assert")
    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_fail_assert.sql").write_text(
        'SCENARIO (description: "failing assertion", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__source__raw__orders AS (\n"
        "  SELECT 0 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__stg_scenario_fail_assert AS (\n"
        "  SELECT 0 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__assert__no_zero_orders AS (\n"
        '  SELECT * FROM __ref("stg_scenario_fail_assert") WHERE order_id = 0\n'
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_failing_expected_dbt_scenario(*, project_dir: Path) -> None:
    """Write a dbt scenario whose expected output mismatches the dbt model."""

    _write_dbt_source_orders_model(project_dir=project_dir, model_name="stg_scenario_fail_expected")
    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_fail_expected.sql").write_text(
        'SCENARIO (description: "failing expected", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__source__raw__orders AS (\n"
        "  SELECT 80 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__stg_scenario_fail_expected AS (\n"
        "  SELECT 999 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_seed_dbt_scenario_targeting_dbt_model(*, project_dir: Path) -> None:
    """Write a dbt seed-backed model and a scenario targeting that dbt model."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    seeds_dir: Path = dbt_project_dir / "seeds"
    seeds_dir.mkdir()
    seeds_dir.joinpath("countries.csv").write_text(
        "country_code,country_name\nUS,United States\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "marts", "dim_scenario_countries.sql").write_text(
        "select country_code, country_name from {{ ref('countries') }}\n",
        encoding="utf-8",
    )
    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_dim_scenario_countries.sql").write_text(
        'SCENARIO (description: "dbt seed scenario", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__seed__countries AS (\n"
        "  SELECT 'MX' AS country_code, 'Mexico' AS country_name\n"
        "),\n"
        "__expected__dim_scenario_countries AS (\n"
        "  SELECT 'MX' AS country_code, 'Mexico' AS country_name\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_ref_boundary_dbt_scenario(*, project_dir: Path) -> None:
    """Write a dbt model chain and a scenario mocking the upstream dbt model as a boundary."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    dbt_project_dir.joinpath("models", "staging", "stg_scenario_boundary.sql").write_text(
        "select order_id, ordered_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "marts", "fact_scenario_boundary.sql").write_text(
        "select order_id, ordered_at from {{ ref('stg_scenario_boundary') }}\n",
        encoding="utf-8",
    )
    schema_path: Path = dbt_project_dir / "models" / "schema.yml"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8")
        + "\nsources:\n"
        + "  - name: raw\n"
        + "    schema: raw\n"
        + "    tables:\n"
        + "      - name: orders\n",
        encoding="utf-8",
    )
    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_fact_scenario_boundary.sql").write_text(
        'SCENARIO (description: "dbt ref boundary scenario", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__dbt_ref__analytics__stg_scenario_boundary AS (\n"
        "  SELECT 90 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__fact_scenario_boundary AS (\n"
        "  SELECT 90 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_qualified_source_dbt_scenario(*, project_dir: Path) -> None:
    """Write colliding dbt package sources and a scenario using a qualified source fixture."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    _write_local_dbt_package(project_dir=project_dir)
    dbt_project_dir.joinpath("models", "staging", "stg_scenario_qualified.sql").write_text(
        "select order_id, ordered_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    schema_path: Path = dbt_project_dir / "models" / "schema.yml"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8")
        + "\nsources:\n"
        + "  - name: raw\n"
        + "    schema: raw\n"
        + "    tables:\n"
        + "      - name: orders\n",
        encoding="utf-8",
    )
    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_stg_scenario_qualified.sql").write_text(
        'SCENARIO (description: "qualified dbt source scenario", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__source__analytics__raw__orders AS (\n"
        "  SELECT 95 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__stg_scenario_qualified AS (\n"
        "  SELECT 95 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_snapshot_boundary_dbt_scenario(*, project_dir: Path) -> None:
    """Write a dbt chain through a snapshot and a scenario mocking the snapshot boundary."""

    _write_dbt_snapshot_chain(project_dir=project_dir)
    scenarios_dir: Path = project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_fact_orders_snapshot_scenario.sql").write_text(
        'SCENARIO (description: "dbt snapshot boundary scenario", tags: ["dbt"]);\n\n'
        "WITH\n"
        "__dbt_ref__analytics__orders_snapshot AS (\n"
        "  SELECT 11 AS order_id, cast('2026-06-02 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__fact_orders_snapshot AS (\n"
        "  SELECT 11 AS order_id, cast('2026-06-02 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def _write_dbt_snapshot_chain(*, project_dir: Path) -> None:
    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    project_path: Path = dbt_project_dir / "dbt_project.yml"
    project_path.write_text(
        project_path.read_text(encoding="utf-8") + "snapshot-paths: ['snapshots']\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "staging", "stg_snapshot_orders.sql").write_text(
        "select 1 as order_id, cast('2026-06-01 00:00:00' as timestamp) as ordered_at\n",
        encoding="utf-8",
    )
    snapshots_dir: Path = dbt_project_dir / "snapshots"
    snapshots_dir.mkdir()
    snapshots_dir.joinpath("orders_snapshot.sql").write_text(
        "{% snapshot orders_snapshot %}\n"
        "{{ config(unique_key='order_id', strategy='check', check_cols=['ordered_at']) }}\n"
        "select order_id, ordered_at from {{ ref('stg_snapshot_orders') }}\n"
        "{% endsnapshot %}\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "marts", "fact_orders_snapshot.sql").write_text(
        "select order_id, ordered_at from {{ ref('orders_snapshot') }}\n",
        encoding="utf-8",
    )


def write_unmocked_snapshot_boundary_dbt_sqlbuild_unit_test(project_dir: Path) -> None:
    """Write a dbt chain through a snapshot with no mock boundary for the snapshot."""

    _write_dbt_snapshot_chain(project_dir=project_dir)
    project_dir.joinpath("tests", "unit", "test_dbt_fact_orders_snapshot.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__dbt_ref__analytics__stg_snapshot_orders AS (\n"
        "  SELECT 1 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__fact_orders_snapshot AS (\n"
        "  SELECT 1 AS order_id, cast('2026-06-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_mocked_snapshot_boundary_dbt_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write a dbt chain through a snapshot mocked as a boundary."""

    _write_dbt_snapshot_chain(project_dir=project_dir)
    project_dir.joinpath("tests", "unit", "test_dbt_fact_orders_snapshot.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__dbt_ref__analytics__orders_snapshot AS (\n"
        "  SELECT 7 AS order_id, cast('2026-06-02 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__fact_orders_snapshot AS (\n"
        "  SELECT 7 AS order_id, cast('2026-06-02 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_qualified_dbt_source_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write colliding dbt package sources and a qualified SQLBuild source fixture test."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    _write_local_dbt_package(project_dir=project_dir)
    dbt_project_dir.joinpath(
        "models", "staging", "stg_orders_from_qualified_source.sql"
    ).write_text(
        "select order_id, ordered_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    schema_path: Path = dbt_project_dir / "models" / "schema.yml"
    schema_path.write_text(
        schema_path.read_text(encoding="utf-8")
        + "\nsources:\n"
        + "  - name: raw\n"
        + "    schema: raw\n"
        + "    tables:\n"
        + "      - name: orders\n",
        encoding="utf-8",
    )
    project_dir.joinpath(
        "tests", "unit", "test_dbt_stg_orders_from_qualified_source.sql"
    ).write_text(
        "TEST();\n\n"
        "WITH\n"
        "__source__analytics__raw__orders AS (\n"
        "  SELECT 40 AS order_id, cast('2026-04-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        "__expected__stg_orders_from_qualified_source AS (\n"
        "  SELECT 40 AS order_id, cast('2026-04-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_qualified_dbt_seed_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write colliding dbt package seeds and a qualified SQLBuild seed fixture test."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    seeds_dir: Path = dbt_project_dir / "seeds"
    seeds_dir.mkdir()
    seeds_dir.joinpath("countries.csv").write_text(
        "country_code,country_name\nUS,United States\n",
        encoding="utf-8",
    )
    _write_local_dbt_package(project_dir=project_dir, include_seed=True)
    dbt_project_dir.joinpath("models", "marts", "dim_qualified_countries.sql").write_text(
        "select country_code, country_name from {{ ref('countries') }}\n",
        encoding="utf-8",
    )
    project_dir.joinpath("tests", "unit", "test_dbt_dim_qualified_countries.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__seed__analytics__countries AS (\n"
        "  SELECT 'BR' AS country_code, 'Brazil' AS country_name\n"
        "),\n"
        "__expected__dim_qualified_countries AS (\n"
        "  SELECT 'BR' AS country_code, 'Brazil' AS country_name\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_dbt_source_relation_collision_sqlbuild_unit_test(project_dir: Path) -> None:
    """Write a dbt source test with a colliding SQLBuild source relation."""

    write_dbt_source_sqlbuild_unit_test(project_dir=project_dir)
    sources_dir: Path = project_dir / "sources"
    sources_dir.mkdir()
    sources_dir.joinpath("local.yml").write_text(
        "sources:\n"
        "  - name: local_orders\n"
        "    database: dbt_interop\n"
        "    schema: raw\n"
        "    table: orders\n",
        encoding="utf-8",
    )


def _write_local_dbt_package(*, project_dir: Path, include_seed: bool = False) -> None:
    """Write a local dbt package used to create package-qualified fixture names."""

    root_dir: Path = project_dir.parent
    dbt_project_dir: Path = root_dir / "dbt_project"
    package_dir: Path = root_dir / "finance_package"
    package_models_dir: Path = package_dir / "models"
    package_models_dir.mkdir(parents=True)
    dbt_project_dir.joinpath("packages.yml").write_text(
        "packages:\n  - local: ../finance_package\n",
        encoding="utf-8",
    )
    package_dir.joinpath("dbt_project.yml").write_text(
        "name: finance\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "seed-paths: ['seeds']\n"
        "seeds:\n"
        "  finance:\n"
        "    +schema: finance\n",
        encoding="utf-8",
    )
    package_models_dir.joinpath("schema.yml").write_text(
        "sources:\n  - name: raw\n    schema: finance_raw\n    tables:\n      - name: orders\n",
        encoding="utf-8",
    )
    if include_seed:
        package_seeds_dir: Path = package_dir / "seeds"
        package_seeds_dir.mkdir()
        package_seeds_dir.joinpath("countries.csv").write_text(
            "country_code,country_name\nFR,France\n",
            encoding="utf-8",
        )


def write_dbt_source_fixture_name_collision_sqlbuild_unit_test(project_dir: Path) -> None:
    """Write a dbt source test with a colliding SQLBuild source fixture name."""

    write_dbt_source_sqlbuild_unit_test(project_dir=project_dir)
    sources_dir: Path = project_dir / "sources"
    sources_dir.mkdir()
    sources_dir.joinpath("local.yml").write_text(
        "sources:\n  - name: raw__orders\n    schema: local_raw\n    table: orders\n",
        encoding="utf-8",
    )


def write_dbt_seed_relation_collision_sqlbuild_unit_test(project_dir: Path) -> None:
    """Write a dbt seed test with a colliding SQLBuild seed relation."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    dbt_project_path: Path = dbt_project_dir / "dbt_project.yml"
    dbt_project_path.write_text(
        dbt_project_path.read_text(encoding="utf-8")
        + "\nseeds:\n"
        + "  analytics:\n"
        + "    local_countries:\n"
        + "      +alias: countries\n",
        encoding="utf-8",
    )
    seeds_dir: Path = dbt_project_dir / "seeds"
    seeds_dir.mkdir()
    seeds_dir.joinpath("local_countries.csv").write_text(
        "country_code,country_name\nUS,United States\n",
        encoding="utf-8",
    )
    dbt_project_dir.joinpath("models", "marts", "dim_local_countries.sql").write_text(
        "select country_code, country_name from {{ ref('local_countries') }}\n",
        encoding="utf-8",
    )
    project_seed_dir: Path = project_dir / "seeds"
    project_seed_dir.mkdir()
    project_seed_dir.joinpath("countries.csv").write_text(
        "country_code,country_name\nCA,Canada\n",
        encoding="utf-8",
    )
    project_seed_dir.joinpath("schema.yml").write_text(
        "seeds:\n"
        "  - name: countries\n"
        "    database: dbt_interop\n"
        "    schema: main\n"
        "    columns:\n"
        "      - name: country_code\n"
        "        type: VARCHAR\n"
        "      - name: country_name\n"
        "        type: VARCHAR\n",
        encoding="utf-8",
    )
    project_dir.joinpath("tests", "unit", "test_dbt_dim_local_countries.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__seed__local_countries AS (\n"
        "  SELECT 'CA' AS country_code, 'Canada' AS country_name\n"
        "),\n"
        "__expected__dim_local_countries AS (\n"
        "  SELECT 'CA' AS country_code, 'Canada' AS country_name\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_dbt_seed_fixture_name_collision_sqlbuild_unit_test(project_dir: Path) -> None:
    """Write a dbt seed test with a colliding SQLBuild seed fixture name."""

    write_dbt_seed_sqlbuild_unit_test(project_dir=project_dir)
    project_seed_dir: Path = project_dir / "seeds"
    project_seed_dir.mkdir()
    project_seed_dir.joinpath("countries.csv").write_text(
        "country_code,country_name\nCA,Canada\n",
        encoding="utf-8",
    )
    project_seed_dir.joinpath("schema.yml").write_text(
        "seeds:\n"
        "  - name: countries\n"
        "    schema: local_seed\n"
        "    columns:\n"
        "      - name: country_code\n"
        "        type: VARCHAR\n"
        "      - name: country_name\n"
        "        type: VARCHAR\n",
        encoding="utf-8",
    )


def compile_dbt_interop_manifest(*, project_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run dbt compile so plain SQLBuild commands can validate dbt refs."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    profiles_dir: Path = project_dir.parent / "profiles"
    target_path: Path = dbt_project_dir / "target"
    return subprocess.run(
        (
            dbt_executable(),
            "compile",
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
            "--target-path",
            target_path.as_posix(),
        ),
        capture_output=True,
        check=False,
        text=True,
    )


def install_dbt_interop_packages(*, project_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run dbt deps for E2E fixtures that add local packages."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    profiles_dir: Path = project_dir.parent / "profiles"
    return subprocess.run(
        (
            dbt_executable(),
            "deps",
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
        ),
        capture_output=True,
        check=False,
        text=True,
    )


def load_json_stdout(stdout: str) -> dict[str, object]:
    """Load JSON command output."""

    payload: object = json.loads(stdout)
    assert isinstance(payload, dict)
    return payload


def assert_dbt_lineage_json_payload(
    *,
    payload: dict[str, object],
    expected_node_ids: tuple[str, ...],
    expected_edges: tuple[tuple[str, str], ...],
    expected_focus: tuple[str, ...],
    expected_direction: str,
    expected_node_metadata: tuple[tuple[str, str, object], ...] = (),
) -> None:
    """Assert stable dbt lineage JSON output."""

    nodes_payload: object = payload["nodes"]
    edges_payload: object = payload["edges"]
    focus_payload: object = payload["focus"]
    assert isinstance(nodes_payload, Sequence)
    assert isinstance(edges_payload, Sequence)
    assert isinstance(focus_payload, Sequence)
    nodes: list[Mapping[str, object]] = [
        cast(Mapping[str, object], node) for node in nodes_payload if isinstance(node, dict)
    ]
    assert [node["id"] for node in nodes] == list(expected_node_ids)
    assert [
        (cast(Mapping[str, object], edge)["from"], cast(Mapping[str, object], edge)["to"])
        for edge in edges_payload
        if isinstance(edge, dict)
    ] == list(expected_edges)
    assert list(focus_payload) == list(expected_focus)
    assert payload["direction"] == expected_direction
    node_by_id: dict[str, Mapping[str, object]] = {str(node["id"]): node for node in nodes}
    for node_id, metadata_key, expected_value in expected_node_metadata:
        assert node_by_id[node_id][metadata_key] == expected_value, (
            node_id,
            metadata_key,
            node_by_id[node_id][metadata_key],
        )


def assert_dbt_column_lineage_json_payload(
    *,
    payload: dict[str, object],
    expected_target: tuple[str, str, str],
    expected_edges: tuple[tuple[str, str], ...],
    expected_direction: str,
    expected_warnings: tuple[str, ...] = (),
) -> None:
    """Assert stable dbt column lineage JSON output."""

    target_payload: object = payload["target"]
    trace_payload: object = payload["trace"]
    metadata_payload: object = payload["metadata"]
    assert isinstance(target_payload, dict)
    assert isinstance(trace_payload, Sequence)
    assert isinstance(metadata_payload, dict)
    target: Mapping[str, object] = cast(Mapping[str, object], target_payload)
    metadata: Mapping[str, object] = cast(Mapping[str, object], metadata_payload)
    assert (
        target["resource_type"],
        target["resource_name"],
        target["column_name"],
    ) == expected_target
    assert [
        (
            _column_payload_id(
                cast(Mapping[str, object], cast(Mapping[str, object], edge)["source"])
            ),
            _column_payload_id(
                cast(Mapping[str, object], cast(Mapping[str, object], edge)["target"])
            ),
        )
        for edge in trace_payload
        if isinstance(edge, dict)
    ] == list(expected_edges)
    assert payload["direction"] == expected_direction
    assert metadata["warnings"] == list(expected_warnings), metadata["warnings"]


def _column_payload_id(column: Mapping[str, object]) -> str:
    return f"{column['resource_name']}:{column['column_name']}"


def remove_dbt_phase11_sqlbuild_models(*, project_dir: Path) -> None:
    """Remove all SQLBuild model files from the focused dbt fixture."""

    model_path: Path
    for model_path in (project_dir / "models").glob("*.sql"):
        model_path.unlink()


def write_dbt_phase11_missing_ref_model(project_dir: Path) -> None:
    """Make dbt compile fail before lineage can load a manifest."""

    (project_dir.parent / "dbt_project" / "models" / "fact_orders.sql").write_text(
        "select order_id from {{ ref('does_not_exist') }}\n",
        encoding="utf-8",
    )


def write_dbt_phase11_invalid_sqlbuild_model(project_dir: Path) -> None:
    """Add a SQLBuild model that only compiles with SQL validation disabled."""

    (project_dir / "models" / "invalid_sql.sql").write_text(
        "MODEL (materialized table);\n\nSELECT FROM\n",
        encoding="utf-8",
    )


def write_dbt_phase11_star_lineage_models(project_dir: Path) -> None:
    """Use SELECT * dbt models to exercise adapter-described source schemas."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    (dbt_models_dir / "stg_orders.sql").write_text(
        "select * from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "fact_orders.sql").write_text(
        "select * from {{ ref('stg_orders') }}\n",
        encoding="utf-8",
    )


def drop_dbt_phase11_orders_source_table(project_dir: Path) -> None:
    """Remove the physical source table while keeping the dbt source definition."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    execute_duckdb(
        db_path=project_dir / "dbt_phase11.duckdb",
        sql="DROP TABLE IF EXISTS main.raw_orders",
    )


def apply_dbt_lineage_error_setup(
    *, project_dir: Path, test_case: DbtLineageErrorE2ETestCase
) -> None:
    """Apply optional setup for a dbt lineage error E2E."""

    if test_case.setup is not None:
        test_case.setup(project_dir)


def query_dbt_phase11_source_freshness_rows(*, project_dir: Path) -> list[tuple[object, ...]]:
    """Return dbt Phase 11 source freshness state rows when the state table exists."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import query_duckdb, table_exists

    db_path: Path = project_dir / "dbt_phase11.duckdb"
    if not table_exists(db_path=db_path, table_name="_sqlbuild_source_freshness"):
        return []
    return query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT source_name, data_version FROM main._sqlbuild_source_freshness "
            "ORDER BY source_name, data_version"
        ),
    )


def query_dbt_phase11_schema_source_freshness_rows(
    *, project_dir: Path, schema: str
) -> list[tuple[object, ...]]:
    """Return dbt Phase 11 source freshness state rows for a specific schema."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import query_duckdb, table_exists

    db_path: Path = project_dir / "dbt_phase11.duckdb"
    if not table_exists(db_path=db_path, table_name="_sqlbuild_source_freshness", schema=schema):
        return []
    return query_duckdb(
        db_path=db_path,
        sql=(
            f"SELECT source_name, data_version FROM {schema}._sqlbuild_source_freshness "
            "ORDER BY source_name, data_version"
        ),
    )


def set_dbt_phase11_sqlbuild_target_schema(*, project_dir: Path, schema: str) -> None:
    """Change the focused Phase 11 SQLBuild target schema."""

    project_file: Path = project_dir / "sqlbuild_project.toml"
    project_file.write_text(
        project_file.read_text(encoding="utf-8").replace('schema = "main"', f'schema = "{schema}"'),
        encoding="utf-8",
    )


def write_dbt_phase11_invalid_downstream_model(*, project_dir: Path) -> None:
    """Make the downstream SQLBuild model fail during warehouse execution."""

    (project_dir / "models" / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT missing_column FROM __dbt_ref("analytics", "fact_orders")\n',
        encoding="utf-8",
    )


def break_dbt_interop_fact_orders_model(project_dir: Path) -> None:
    """Make the dbt fact_orders model fail at run time so the dbt build errors."""

    fact_orders_path: Path = (
        project_dir.parent / "dbt_project" / "models" / "marts" / "fact_orders.sql"
    )
    fact_orders_path.write_text(
        "{{ config(tags=['finance']) }}\n"
        "select * from this_relation_does_not_exist_for_failure_test\n",
        encoding="utf-8",
    )


def add_dbt_phase11_payments_branch(*, project_dir: Path) -> None:
    """Add a dbt model that depends on orders and payments sources."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    sqlbuild_models_dir: Path = project_dir / "models"
    sources_path: Path = dbt_models_dir / "sources.yml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8")
        + "      - name: payments\n"
        + "        identifier: raw_payments\n"
        + "        config:\n"
        + "          loaded_at_field: loaded_at\n"
        + "          freshness:\n"
        + "            error_after: {count: 1, period: day}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "order_payments.sql").write_text(
        "select o.order_id, o.amount as order_amount, p.payment_amount "
        "from {{ source('raw', 'orders') }} o "
        "join {{ source('raw', 'payments') }} p using (order_id)\n",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "payment_summary.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id, payment_amount FROM __dbt_ref("analytics", "order_payments")\n',
        encoding="utf-8",
    )


def add_dbt_phase11_query_filter_branch(*, project_dir: Path) -> None:
    """Add dbt sources that exercise loaded_at_query and freshness filter translation."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    sqlbuild_models_dir: Path = project_dir / "models"
    sources_path: Path = dbt_models_dir / "sources.yml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8")
        + "      - name: query_events\n"
        + "        identifier: raw_query_events\n"
        + "        config:\n"
        + "          loaded_at_query: SELECT MAX(loaded_at) AS loaded_at "
        + "FROM main.raw_query_events\n"
        + "          freshness:\n"
        + "            error_after: {count: 1, period: day}\n"
        + "      - name: filtered_events\n"
        + "        identifier: raw_filtered_events\n"
        + "        config:\n"
        + "          loaded_at_field: loaded_at\n"
        + "          freshness:\n"
        + "            error_after: {count: 1, period: day}\n"
        + "            filter: include_in_freshness\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "event_rollup.sql").write_text(
        "select event_id, event_amount from {{ source('raw', 'query_events') }}\n"
        "union all\n"
        "select event_id, event_amount from {{ source('raw', 'filtered_events') }}\n",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "event_summary.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT event_id, event_amount FROM __dbt_ref("analytics", "event_rollup")\n',
        encoding="utf-8",
    )


def prepare_dbt_phase11_project(*, tmp_path: Path, replay_on_change: str | None = None) -> Path:
    """Write a focused dbt interop project for model-planning E2Es."""

    root_dir: Path = tmp_path / "dbt_phase11"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    dbt_seeds_dir: Path = dbt_project_dir / "seeds"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    dbt_models_dir.mkdir(parents=True)
    dbt_seeds_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)

    db_path: Path = sqlbuild_project_dir / "dbt_phase11.duckdb"
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n",
        encoding="utf-8",
    )
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "seed-paths: ['seeds']\n"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    (dbt_seeds_dir / "country_codes.csv").write_text(
        "country_code,country_name\nUS,United States\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "sources.yml").write_text(
        "version: 2\n"
        "sources:\n"
        "  - name: raw\n"
        "    schema: main\n"
        "    tables:\n"
        "      - name: orders\n"
        "        identifier: raw_orders\n"
        "        config:\n"
        "          loaded_at_field: loaded_at\n"
        "          freshness:\n"
        "            error_after: {count: 1, period: day}\n"
        "      - name: customers\n"
        "        identifier: raw_customers\n",
        encoding="utf-8",
    )
    write_dbt_phase11_fact_orders_model(
        project_dir=sqlbuild_project_dir, amount_expression="amount"
    )
    (dbt_models_dir / "stg_orders.sql").write_text(
        "select order_id, customer_id, amount, loaded_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "stg_customers.sql").write_text(
        "select customer_id, customer_name from {{ source('raw', 'customers') }}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "dim_customers.sql").write_text(
        "select customer_id, customer_name from {{ ref('stg_customers') }}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "schema.yml").write_text(
        "version: 2\n"
        "models:\n"
        "  - name: fact_orders\n"
        "    columns:\n"
        "      - name: order_id\n"
        "        tests: [not_null]\n"
        "  - name: dim_customers\n"
        "    columns:\n"
        "      - name: customer_id\n"
        "        tests: [not_null]\n",
        encoding="utf-8",
    )
    replay_line: str = (
        f'replay_on_change = "{replay_on_change}"\n' if replay_on_change is not None else ""
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(
        'name = "dbt_phase11"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        'database = "dbt_phase11.duckdb"\n'
        "[targets.dev]\n"
        'schema = "main"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n'
        f"{replay_line}",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id, amount AS downstream_amount FROM __dbt_ref("analytics", "fact_orders")\n',
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "customer_summary.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT customer_id, customer_name FROM __dbt_ref("analytics", "dim_customers")\n',
        encoding="utf-8",
    )
    seed_dbt_phase11_sources(project_dir=sqlbuild_project_dir, stale_orders=False)
    return sqlbuild_project_dir


def prepare_dbt_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a focused DuckDB dbt reuse_from project with a local prod git ref."""

    root_dir: Path = tmp_path / "dbt_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_reuse_from.duckdb"
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: main\n"
        "    prod:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: prod\n",
        encoding="utf-8",
    )
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
    write_dbt_reuse_from_fact_orders_model(project_dir=sqlbuild_project_dir, amount=900)
    (dbt_models_dir / "unrelated_model.sql").write_text(
        "select 77 as unrelated_id\n",
        encoding="utf-8",
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(
        'name = "dbt_reuse_from"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        'database = "dbt_reuse_from.duckdb"\n'
        "[targets.dev]\n"
        'schema = "main"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n'
        "[dbt.reuse_from]\n"
        'git_ref = "prod"\n'
        'generate_schema_name_override = "dbt/macros/prod_generate_schema_name.sql"\n',
        encoding="utf-8",
    )
    (macro_dir / "prod_generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n  prod\n{%- endmacro %}\n",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id, amount AS downstream_amount FROM __dbt_ref("analytics", "fact_orders")\n',
        encoding="utf-8",
    )
    _run_git(args=("init",), cwd=root_dir)
    _run_git(args=("config", "user.email", "sqlbuild@example.invalid"), cwd=root_dir)
    _run_git(args=("config", "user.name", "SQLBuild Test"), cwd=root_dir)
    _run_git(args=("add", "."), cwd=root_dir)
    _run_git(args=("commit", "-m", "prod baseline"), cwd=root_dir)
    _run_git(args=("branch", "prod"), cwd=root_dir)
    subprocess.run(
        (
            dbt_executable(),
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
        text=True,
    )
    return sqlbuild_project_dir


def prepare_dbt_seeded_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a focused DuckDB dbt reuse_from project for seeded incremental reuse."""

    root_dir: Path = tmp_path / "dbt_seeded_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_seeded_reuse_from.duckdb"
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: main\n"
        "    prod:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: prod\n",
        encoding="utf-8",
    )
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\nversion: '1.0'\nprofile: analytics\nmodel-paths: ['models']\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "fact_orders.sql").write_text(
        "{{ config(materialized='incremental', "
        "meta={'sqlbuild': {'reuse_cursor': 'event_time'}}) }}\n"
        "select order_id, amount, event_time from main.raw_orders\n"
        "{% if is_incremental() %}\n"
        "where event_time > (select max(event_time) from {{ this }})\n"
        "{% endif %}\n",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id, amount AS downstream_amount FROM __dbt_ref("analytics", "fact_orders")\n',
        encoding="utf-8",
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(
        'name = "dbt_seeded_reuse_from"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        'database = "dbt_seeded_reuse_from.duckdb"\n'
        "[targets.dev]\n"
        'schema = "main"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n'
        "[dbt.reuse_from]\n"
        'git_ref = "prod"\n'
        'generate_schema_name_override = "dbt/macros/prod_generate_schema_name.sql"\n',
        encoding="utf-8",
    )
    (macro_dir / "prod_generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n  prod\n{%- endmacro %}\n",
        encoding="utf-8",
    )
    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE TABLE main.raw_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time"
        ),
    )
    _run_git(args=("init",), cwd=root_dir)
    _run_git(args=("config", "user.email", "sqlbuild@example.invalid"), cwd=root_dir)
    _run_git(args=("config", "user.name", "SQLBuild Test"), cwd=root_dir)
    _run_git(args=("add", "."), cwd=root_dir)
    _run_git(args=("commit", "-m", "prod seeded baseline"), cwd=root_dir)
    _run_git(args=("branch", "prod"), cwd=root_dir)
    subprocess.run(
        (
            dbt_executable(),
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
        text=True,
    )
    execute_duckdb(
        db_path=db_path,
        sql=("INSERT INTO main.raw_orders VALUES (2, 901, TIMESTAMP '2026-01-02')"),
    )
    return sqlbuild_project_dir


def prepare_dbt_multi_node_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a DuckDB dbt reuse_from project with three reusable table models."""

    root_dir: Path = tmp_path / "dbt_multi_node_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_multi_node_reuse_from.duckdb"
    _write_reuse_from_profiles(profiles_dir=profiles_dir, db_path=db_path)
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
    model_name: str
    for model_name in ("orders_a", "orders_b", "orders_c"):
        (dbt_models_dir / f"{model_name}.sql").write_text(
            f"select '{model_name}' as model_name, 900 as amount\n",
            encoding="utf-8",
        )
    _write_reuse_from_sqlbuild_project(
        sqlbuild_project_dir=sqlbuild_project_dir,
        project_name="dbt_multi_node_reuse_from",
        database_name="dbt_multi_node_reuse_from.duckdb",
    )
    _write_prod_schema_macro(macro_dir=macro_dir)
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT model_name, amount AS downstream_amount FROM __dbt_ref("analytics", "orders_a")\n'
        "UNION ALL\n"
        'SELECT model_name, amount AS downstream_amount FROM __dbt_ref("analytics", "orders_b")\n'
        "UNION ALL\n"
        'SELECT model_name, amount AS downstream_amount FROM __dbt_ref("analytics", "orders_c")\n',
        encoding="utf-8",
    )
    _initialize_reuse_from_git(root_dir=root_dir)
    _run_dbt(
        args=("run",), dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target="prod"
    )
    return sqlbuild_project_dir


def prepare_dbt_multi_node_seeded_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a DuckDB dbt reuse_from project with three seeded incremental models."""

    root_dir: Path = tmp_path / "dbt_multi_node_seeded_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_multi_node_seeded_reuse_from.duckdb"
    _write_reuse_from_profiles(profiles_dir=profiles_dir, db_path=db_path)
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\nversion: '1.0'\nprofile: analytics\nmodel-paths: ['models']\n",
        encoding="utf-8",
    )
    model_name: str
    for model_name in ("orders_a", "orders_b", "orders_c"):
        (dbt_models_dir / f"{model_name}.sql").write_text(
            "{{ config(materialized='incremental', "
            "meta={'sqlbuild': {'reuse_cursor': 'event_time'}}) }}\n"
            f"select model_name, order_id, amount, event_time from main.raw_{model_name}\n"
            "{% if is_incremental() %}\n"
            "where event_time > (select max(event_time) from {{ this }})\n"
            "{% endif %}\n",
            encoding="utf-8",
        )
    _write_reuse_from_sqlbuild_project(
        sqlbuild_project_dir=sqlbuild_project_dir,
        project_name="dbt_multi_node_seeded_reuse_from",
        database_name="dbt_multi_node_seeded_reuse_from.duckdb",
    )
    _write_prod_schema_macro(macro_dir=macro_dir)
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        "SELECT model_name, order_id, amount AS downstream_amount "
        'FROM __dbt_ref("analytics", "orders_a")\n'
        "UNION ALL\n"
        "SELECT model_name, order_id, amount AS downstream_amount "
        'FROM __dbt_ref("analytics", "orders_b")\n'
        "UNION ALL\n"
        "SELECT model_name, order_id, amount AS downstream_amount "
        'FROM __dbt_ref("analytics", "orders_c")\n',
        encoding="utf-8",
    )
    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    seed_sql_parts: list[str] = []
    for model_name in ("orders_a", "orders_b", "orders_c"):
        seed_sql_parts.append(
            f"CREATE TABLE main.raw_{model_name} AS "
            f"SELECT '{model_name}' AS model_name, 1 AS order_id, 900 AS amount, "
            "TIMESTAMP '2026-01-01' AS event_time"
        )
    execute_duckdb(db_path=db_path, sql="; ".join(seed_sql_parts))
    _initialize_reuse_from_git(root_dir=root_dir)
    _run_dbt(
        args=("run",), dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target="prod"
    )
    for model_name in ("orders_a", "orders_b", "orders_c"):
        execute_duckdb(
            db_path=db_path,
            sql=(
                f"INSERT INTO main.raw_{model_name} VALUES "
                f"('{model_name}', 2, 901, TIMESTAMP '2026-01-02')"
            ),
        )
    return sqlbuild_project_dir


def prepare_dbt_snapshot_seeded_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a DuckDB dbt reuse_from project with a seeded dbt snapshot."""

    root_dir: Path = tmp_path / "dbt_snapshot_seeded_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    snapshots_dir: Path = dbt_project_dir / "snapshots"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    snapshots_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_snapshot_seeded_reuse_from.duckdb"
    _write_reuse_from_profiles(profiles_dir=profiles_dir, db_path=db_path)
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "snapshot-paths: ['snapshots']\n",
        encoding="utf-8",
    )
    _write_dbt_orders_snapshot(snapshots_dir=snapshots_dir, target_schema="prod")
    _write_reuse_from_sqlbuild_project(
        sqlbuild_project_dir=sqlbuild_project_dir,
        project_name="dbt_snapshot_seeded_reuse_from",
        database_name="dbt_snapshot_seeded_reuse_from.duckdb",
    )
    _write_prod_schema_macro(macro_dir=macro_dir)
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        "SELECT order_id, amount AS downstream_amount "
        'FROM __dbt_ref("analytics", "orders_snapshot") '
        "WHERE dbt_valid_to IS NULL\n",
        encoding="utf-8",
    )
    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE TABLE main.raw_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time"
        ),
    )
    _initialize_reuse_from_git(root_dir=root_dir)
    _run_dbt(
        args=("snapshot",),
        dbt_project_dir=dbt_project_dir,
        profiles_dir=profiles_dir,
        target="prod",
    )
    _write_dbt_orders_snapshot(snapshots_dir=snapshots_dir, target_schema="main")
    execute_duckdb(
        db_path=db_path,
        sql="INSERT INTO main.raw_orders VALUES (2, 901, TIMESTAMP '2026-01-02')",
    )
    return sqlbuild_project_dir


def _write_reuse_from_profiles(*, profiles_dir: Path, db_path: Path) -> None:
    profiles_dir.joinpath("profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: main\n"
        "    prod:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: prod\n",
        encoding="utf-8",
    )


def _write_reuse_from_sqlbuild_project(
    *, sqlbuild_project_dir: Path, project_name: str, database_name: str
) -> None:
    sqlbuild_project_dir.joinpath("sqlbuild_project.toml").write_text(
        f'name = "{project_name}"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        f'database = "{database_name}"\n'
        "[targets.dev]\n"
        'schema = "main"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n'
        "[dbt.reuse_from]\n"
        'git_ref = "prod"\n'
        'generate_schema_name_override = "dbt/macros/prod_generate_schema_name.sql"\n',
        encoding="utf-8",
    )


def _write_prod_schema_macro(*, macro_dir: Path) -> None:
    macro_dir.joinpath("prod_generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n  prod\n{%- endmacro %}\n",
        encoding="utf-8",
    )


def _write_dbt_orders_snapshot(*, snapshots_dir: Path, target_schema: str) -> None:
    snapshots_dir.joinpath("orders_snapshot.sql").write_text(
        "{% snapshot orders_snapshot %}\n"
        "{{ config(\n"
        f"  target_schema='{target_schema}',\n"
        "  unique_key='order_id',\n"
        "  strategy='timestamp',\n"
        "  updated_at='event_time',\n"
        "  meta={'sqlbuild': {'reuse_cursor': 'event_time'}}\n"
        ") }}\n"
        "select order_id, amount, event_time from main.raw_orders\n"
        "{% endsnapshot %}\n",
        encoding="utf-8",
    )


def _initialize_reuse_from_git(*, root_dir: Path) -> None:
    _run_git(args=("init",), cwd=root_dir)
    _run_git(args=("config", "user.email", "sqlbuild@example.invalid"), cwd=root_dir)
    _run_git(args=("config", "user.name", "SQLBuild Test"), cwd=root_dir)
    _run_git(args=("add", "."), cwd=root_dir)
    _run_git(args=("commit", "-m", "prod baseline"), cwd=root_dir)
    _run_git(args=("branch", "prod"), cwd=root_dir)


def _run_dbt(
    *, args: tuple[str, ...], dbt_project_dir: Path, profiles_dir: Path, target: str
) -> None:
    subprocess.run(
        (
            dbt_executable(),
            *args,
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
            "--target",
            target,
        ),
        capture_output=True,
        check=True,
        text=True,
    )


def write_dbt_reuse_from_fact_orders_model(*, project_dir: Path, amount: int) -> None:
    """Write the mutable dbt model used by reuse_from E2Es."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    (dbt_models_dir / "fact_orders.sql").write_text(
        f"select 1 as order_id, {amount} as amount\n",
        encoding="utf-8",
    )


def _run_git(*, args: tuple[str, ...], cwd: Path) -> None:
    subprocess.run(("git", *args), cwd=cwd, capture_output=True, check=True, text=True)


def add_dbt_phase11_sqlbuild_function_branch(*, project_dir: Path) -> None:
    """Add a SQLBuild UDF branch downstream of the dbt orders model."""

    functions_dir: Path = project_dir / "functions" / "sql"
    models_dir: Path = project_dir / "models"
    functions_dir.mkdir(parents=True, exist_ok=True)
    (functions_dir / "is_large_amount.sql").write_text(
        "FUNCTION (\n  arguments (amount INTEGER),\n  returns BOOLEAN,\n);\n\namount > 50\n",
        encoding="utf-8",
    )
    (models_dir / "amount_quality.sql").write_text(
        "MODEL (materialized table);\n\n"
        "SELECT\n"
        "  order_id,\n"
        '  __udf("is_large_amount")(downstream_amount) AS is_large_amount\n'
        'FROM __ref("downstream_orders")\n',
        encoding="utf-8",
    )


def write_dbt_phase11_fact_orders_model(*, project_dir: Path, amount_expression: str) -> None:
    """Write the mutable dbt fact_orders model used by Phase 11 E2Es."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    (dbt_models_dir / "fact_orders.sql").write_text(
        "select order_id, customer_id, "
        f"{amount_expression} as amount from {{{{ ref('stg_orders') }}}}\n",
        encoding="utf-8",
    )


def seed_dbt_phase11_sources(*, project_dir: Path, stale_orders: bool) -> None:
    """Create raw DuckDB tables for the focused Phase 11 dbt project."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    loaded_at: str = "2000-01-01 00:00:00" if stale_orders else "2999-01-01 00:00:00"
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_orders AS "
            "SELECT 1 AS order_id, 10 AS customer_id, 100 AS amount, "
            f"TIMESTAMP '{loaded_at}' AS loaded_at"
        ),
    )
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 10 AS customer_id, 'Ada' AS customer_name"
        ),
    )


def assert_dbt_scenario_snapshot(
    *,
    project_dir: Path,
    scenario_name: str,
    relation_file: str,
    expected_row_count: int,
    expected_column_names: set[str],
) -> None:
    """Assert a captured dbt scenario snapshot manifest and relation JSONL file."""

    snapshot_root: Path = project_dir / "tests" / "_scenario_snapshots" / scenario_name
    manifest_path: Path = snapshot_root / "scenario.json"
    jsonl_path: Path = snapshot_root / relation_file
    assert manifest_path.exists()
    assert jsonl_path.exists()
    manifest_data: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest_data, dict)
    assert manifest_data["scenario_name"] == scenario_name
    assert manifest_data["format"] == "jsonl"
    assert manifest_data["total_rows"] == expected_row_count
    relation: object = manifest_data["relations"][0]
    assert isinstance(relation, dict)
    assert relation["file"] == relation_file
    assert relation["row_count"] == expected_row_count
    columns: object = relation["columns"]
    assert isinstance(columns, list)
    column_names: set[str] = {str(column["name"]) for column in columns}
    assert expected_column_names.issubset(column_names)
    column: object
    for column in columns:
        assert isinstance(column, dict)
        assert column["warehouse_type"]
        assert column["local_type"]
    rows: list[str] = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == expected_row_count


def assert_dbt_local_replay_rows(
    *,
    project_dir: Path,
    scenario_name: str,
    rows_sql: str,
    expected_rows: tuple[tuple[object, ...], ...],
) -> None:
    """Assert replayed rows in the retained local DuckDB for a dbt scenario."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import query_duckdb

    if not rows_sql:
        return
    db_path: Path = project_dir / "target" / "run" / "scenarios" / scenario_name / "local.duckdb"
    rows: list[tuple[object, ...]] = query_duckdb(db_path=db_path, sql=rows_sql)
    assert tuple(rows) == expected_rows
