from __future__ import annotations

import subprocess
from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
)


def prepare_virtual_clone_project(tmp_path: Path) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_clone_project",
        repo_files={
            "sqlbuild_project.toml": build_virtual_clone_project_toml(),
            "sqlbuild_local.toml": 'target = "dev"\n',
            "models/stg_orders.sql": "MODEL ();\n\nSELECT 7 AS id\n",
            "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
            "models/dim_customers.sql": "MODEL ();\n\nSELECT 1 AS customer_id\n",
        },
    )


def build_virtual_clone_project_toml() -> str:
    return (
        'name = "virtual_clone_project"\n'
        'adapter = "duckdb"\n'
        "[settings]\n"
        "virtual_environments = true\n"
        'default_target = "dev"\n\n'
        "[connection]\n"
        'database = "dev.duckdb"\n\n'
        "[targets.prod]\n"
        'schema = "prod"\n\n'
        "[targets.prod.connection]\n"
        'database = "prod.duckdb"\n\n'
        "[targets.prod.clone]\n"
        "allow_as_source = true\n\n"
        "[targets.prod.state]\n"
        'backend = "duckdb"\n'
        'schema = "sqlbuild_state"\n\n'
        "[targets.prod.state.connection]\n"
        'database = "prod_state.duckdb"\n\n'
        "[targets.dev]\n"
        'schema = "dev"\n\n'
        "[targets.dev.connection]\n"
        'database = "dev.duckdb"\n\n'
        "[targets.dev.clone]\n"
        "allow_as_target = true\n\n"
        "[targets.dev.state]\n"
        'backend = "duckdb"\n'
        'schema = "sqlbuild_state"\n\n'
        "[targets.dev.state.connection]\n"
        'database = "dev_state.duckdb"\n'
    )


def build_prod_source_versions(project_dir: Path) -> None:
    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stderr


def build_dev_target_versions(project_dir: Path) -> None:
    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stderr


def init_dev_state(project_dir: Path) -> None:
    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr


def prod_version_hash(project_dir: Path, model_name: str) -> str:
    return str(
        query_duckdb(
            db_path=project_dir / "prod_state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_refs "
                f"WHERE virtual_target_name = 'prod' AND model_name = '{model_name}'"
            ),
        )[0][0]
    )


def dev_version_hash(project_dir: Path, model_name: str) -> str:
    return str(
        query_duckdb(
            db_path=project_dir / "dev_state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_refs "
                f"WHERE virtual_target_name = 'dev' AND model_name = '{model_name}'"
            ),
        )[0][0]
    )


def dev_ref_rows(project_dir: Path) -> list[tuple[object, ...]]:
    return query_duckdb(
        db_path=project_dir / "dev_state.duckdb",
        sql=(
            "SELECT model_name, version_hash FROM sqlbuild_state.virtual_environment_refs "
            "WHERE virtual_target_name = 'dev' ORDER BY model_name"
        ),
    )


def target_physical_relation_count(project_dir: Path) -> int:
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "dev.duckdb",
        sql=(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'dev__sqb_physical' AND table_name LIKE '%__v_%'"
        ),
    )
    return len(rows)


def insert_dev_model_version_lock(*, project_dir: Path, model_name: str, version_hash: str) -> None:
    execute_duckdb(
        db_path=project_dir / "dev_state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
            f"('model_version:{model_name}:{version_hash}', 'test', "
            "CURRENT_TIMESTAMP + INTERVAL 1 HOUR, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )
