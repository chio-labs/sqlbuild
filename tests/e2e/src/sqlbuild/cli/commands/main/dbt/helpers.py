from __future__ import annotations

import json
import os
import pty
import subprocess
import threading
from collections.abc import Callable
from functools import partial
from pathlib import Path
from shutil import copytree
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import REPO_ROOT

DBT_INTEROP_FIXTURE_DIR: Path = REPO_ROOT / "tests" / "e2e" / "fixtures" / "dbt_interop"


def dbt_executable() -> str:
    """Return the dbt executable for e2e tests, honoring DBT_EXECUTABLE."""

    return os.environ.get("DBT_EXECUTABLE", "dbt").strip() or "dbt"


def skip_unless_dbt_is_runnable() -> None:
    """Skip e2e dbt tests when the dbt CLI is unavailable."""

    try:
        subprocess.run(
            (dbt_executable(), "--version"),
            capture_output=True,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        pytest.skip(f"dbt CLI is not runnable: {error.stderr or error.stdout}")


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

    _run_git(args=("init", "--initial-branch=main"), cwd=workspace)
    _run_git(args=("config", "user.email", "sqlbuild@example.invalid"), cwd=workspace)
    _run_git(args=("config", "user.name", "SQLBuild Test"), cwd=workspace)
    _run_git(args=("add", "."), cwd=workspace)
    _run_git(args=("commit", "-m", "prod baseline"), cwd=workspace)
    _run_git(args=("update-ref", f"refs/heads/{production_ref}", "HEAD"), cwd=workspace)
    _run_git(args=("checkout", "-b", "feature"), cwd=workspace)


def _capture_pty_output(
    *, master_fd: int, output_parts: list[bytes], reader_done: threading.Event
) -> None:
    try:
        for chunk in iter(partial(os.read, master_fd, 4096), b""):
            output_parts.append(chunk)
    except OSError:
        return
    finally:
        reader_done.set()


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
    reader_done: threading.Event = threading.Event()
    reader: threading.Thread = threading.Thread(
        target=_capture_pty_output,
        kwargs={"master_fd": master_fd, "output_parts": output_parts, "reader_done": reader_done},
        daemon=True,
    )
    reader.start()
    try:
        os.write(master_fd, input_text.encode())
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise subprocess.TimeoutExpired(command, timeout_seconds) from None
    finally:
        reader_done.wait(timeout=1.0)
        os.close(master_fd)
        reader.join(timeout=1.0)
    output: str = b"".join(output_parts).decode(errors="replace")
    return subprocess.CompletedProcess(
        args=("sqb", *command),
        returncode=cast(int, process.returncode),
        stdout=output,
        stderr="",
    )


def prepare_dbt_interop_project(*, tmp_path: Path) -> Path:
    """Copy the reusable dbt interop fixture and return its SQLBuild project root."""

    root_dir: Path = tmp_path / "dbt_interop"
    copytree(DBT_INTEROP_FIXTURE_DIR, root_dir)
    local_config_path: Path = root_dir / "sqlbuild_project" / "sqlbuild_local.toml"
    local_config_path.unlink(missing_ok=True)
    db_path: Path = root_dir / "sqlbuild_project" / "dbt_interop.duckdb"
    db_path.unlink(missing_ok=True)
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


def write_double_underscore_dbt_model_sqlbuild_unit_test(*, project_dir: Path) -> None:
    """Write a direct dbt target whose model name contains double underscores."""

    model_name: str = "race__int_enriched__course_match_graph"
    project_dir.parent.joinpath("dbt_project", "models", "marts", f"{model_name}.sql").write_text(
        "select order_id, ordered_at from {{ ref('stg_orders') }}\n",
        encoding="utf-8",
    )
    project_dir.joinpath("tests", "unit", f"test_dbt_{model_name}.sql").write_text(
        "TEST();\n\n"
        "WITH\n"
        "__dbt_ref__stg_orders AS (\n"
        "  SELECT 10 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at\n"
        "),\n"
        f"__expected__{model_name} AS (\n"
        "  SELECT 10 AS order_id, cast('2026-01-01 00:00:00' as timestamp) AS ordered_at\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def write_sqlbuild_defer_target_models(*, project_dir: Path) -> None:
    """Configure native SQLBuild target deferral inside a dbt interop fixture."""

    config_path: Path = project_dir / "sqlbuild_project.toml"
    config_text: str = config_path.read_text(encoding="utf-8").replace(
        'adapter = "duckdb"\n',
        'adapter = "duckdb"\ndefault_target = "dev"\n',
    )
    config_path.write_text(
        config_text
        + "\n[targets.dev]\n"
        + 'schema = "dev"\n\n'
        + "[targets.prod]\n"
        + 'schema = "prod"\n',
        encoding="utf-8",
    )
    project_dir.joinpath("models", "deferred_upstream.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 42 AS order_id\n",
        encoding="utf-8",
    )
    project_dir.joinpath("models", "deferred_consumer.sql").write_text(
        'MODEL (materialized table);\n\nSELECT order_id FROM __ref("deferred_upstream")\n',
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
    seed_contents: str
    for seed_contents in {False: (), True: ("country_code,country_name\nFR,France\n",)}[
        include_seed
    ]:
        package_seeds_dir: Path = package_dir / "seeds"
        package_seeds_dir.mkdir()
        package_seeds_dir.joinpath("countries.csv").write_text(
            seed_contents,
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


def _run_git(*, args: tuple[str, ...], cwd: Path) -> None:
    subprocess.run(("git", *args), cwd=cwd, capture_output=True, check=True, text=True)


def assert_dbt_local_replay_rows(
    *,
    project_dir: Path,
    scenario_name: str,
    rows_sql: str,
    expected_rows: tuple[tuple[object, ...], ...],
) -> None:
    """Assert replayed rows in the retained local DuckDB for a dbt scenario."""

    assertion_strategy: Callable[..., None] = {
        False: _skip_dbt_local_replay_row_assertion,
        True: _assert_dbt_local_replay_row_query,
    }[bool(rows_sql)]
    assertion_strategy(
        project_dir=project_dir,
        scenario_name=scenario_name,
        rows_sql=rows_sql,
        expected_rows=expected_rows,
    )


def _skip_dbt_local_replay_row_assertion(**_kwargs: object) -> None:
    return


def _assert_dbt_local_replay_row_query(
    *,
    project_dir: Path,
    scenario_name: str,
    rows_sql: str,
    expected_rows: tuple[tuple[object, ...], ...],
) -> None:
    from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import query_duckdb

    db_path: Path = project_dir / "target" / "run" / "scenarios" / scenario_name / "local.duckdb"
    rows: list[tuple[object, ...]] = query_duckdb(db_path=db_path, sql=rows_sql)
    assert tuple(rows) == expected_rows
