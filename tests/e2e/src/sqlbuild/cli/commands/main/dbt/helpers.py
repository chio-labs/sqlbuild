from __future__ import annotations

import json
import subprocess
from pathlib import Path
from shutil import copytree

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import REPO_ROOT

DBT_INTEROP_FIXTURE_DIR: Path = REPO_ROOT / "tests" / "e2e" / "fixtures" / "dbt_interop"


def skip_unless_dbt_is_runnable() -> None:
    """Skip e2e dbt tests when the dbt CLI is unavailable."""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        ("dbt", "--version"),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"dbt CLI is not runnable: {result.stderr or result.stdout}")


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


def compile_dbt_interop_manifest(*, project_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run dbt compile so plain SQLBuild commands can validate dbt refs."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    profiles_dir: Path = project_dir.parent / "profiles"
    target_path: Path = dbt_project_dir / "target"
    return subprocess.run(
        (
            "dbt",
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


def load_json_stdout(stdout: str) -> dict[str, object]:
    """Load JSON command output."""

    payload: object = json.loads(stdout)
    assert isinstance(payload, dict)
    return payload


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
        "        loaded_at_field: loaded_at\n"
        "        freshness:\n"
        "          error_after: {count: 1, period: day}\n"
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
        text=True,
    )
    write_dbt_reuse_from_fact_orders_model(project_dir=sqlbuild_project_dir, amount=111)
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
        text=True,
    )
    execute_duckdb(
        db_path=db_path,
        sql=("INSERT INTO main.raw_orders VALUES (2, 901, TIMESTAMP '2026-01-02')"),
    )
    return sqlbuild_project_dir


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
