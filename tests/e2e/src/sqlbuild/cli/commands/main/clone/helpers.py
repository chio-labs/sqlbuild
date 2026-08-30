from __future__ import annotations

import subprocess
from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
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
            "seeds/orders.yml": (
                "seeds:\n"
                "  - name: order_amounts\n"
                "    path: order_amounts.csv\n"
                "    columns:\n"
                "      - name: id\n"
                "        type: integer\n"
            ),
            "seeds/order_amounts.csv": "id\n7\n",
            "models/stg_orders.sql": 'MODEL ();\n\nSELECT id FROM __seed("order_amounts")\n',
            "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
            "models/dim_customers.sql": "MODEL ();\n\nSELECT 1 AS customer_id\n",
        },
    )


def prepare_virtual_source_clone_project(tmp_path: Path) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_clone_project",
        repo_files={
            "sqlbuild_project.toml": build_virtual_clone_project_toml(),
            "sqlbuild_local.toml": 'target = "dev"\n',
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    schema: raw\n"
                "    table: raw_orders\n"
                "    columns:\n"
                "      - name: id\n"
                "        type: integer\n"
                "      - name: data_version\n"
                "        type: integer\n"
                "    freshness:\n"
                "      strategy: column\n"
                "      column: data_version\n"
                "      type: integer\n"
            ),
            "models/source_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )


def build_virtual_clone_project_toml() -> str:
    return (
        'name = "virtual_clone_project"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n\n'
        "[settings]\n"
        "virtual_environments = true\n\n"
        "[connection]\n"
        'database = "dev.duckdb"\n\n'
        "[targets.prod]\n"
        'schema = "prod"\n\n'
        "[targets.prod.connection]\n"
        'database = "dev.duckdb"\n\n'
        "[targets.prod.clone]\n"
        "allow_as_clone_origin = true\n\n"
        "[targets.prod.state]\n"
        'backend = "duckdb"\n'
        'schema = "sqlbuild_state"\n\n'
        "[targets.prod.state.connection]\n"
        'database = "dev_state.duckdb"\n\n'
        "[targets.dev]\n"
        'schema = "dev"\n\n'
        "[targets.dev.connection]\n"
        'database = "dev.duckdb"\n\n'
        "[targets.dev.clone]\n"
        "allow_as_clone_destination = true\n\n"
        "[targets.dev.state]\n"
        'backend = "duckdb"\n'
        'schema = "sqlbuild_state"\n\n'
        "[targets.dev.state.connection]\n"
        'database = "dev_state.duckdb"\n'
    )


def build_prod_source_versions(project_dir: Path) -> None:
    from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stderr
    project_config_path: Path = project_dir / "sqlbuild_project.toml"
    project_config_path.write_text(
        project_config_path.read_text(encoding="utf-8")
        .replace(
            '[targets.prod.connection]\ndatabase = "dev.duckdb"',
            "[targets.prod.connection]\n"
            'database = "${ENV:SQLBUILD_TEST_UNUSED_VIRTUAL_ORIGIN_DATABASE}"',
        )
        .replace(
            '[targets.prod.state.connection]\ndatabase = "dev_state.duckdb"',
            "[targets.prod.state.connection]\n"
            'database = "${ENV:SQLBUILD_TEST_UNUSED_VIRTUAL_ORIGIN_STATE_DATABASE}"',
        ),
        encoding="utf-8",
    )


def build_dev_target_versions(project_dir: Path) -> None:
    from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

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
    from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr


def prod_version_hash(project_dir: Path, model_name: str) -> str:
    return str(
        query_duckdb(
            db_path=project_dir / "dev_state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_node_refs "
                "WHERE virtual_environment_name = 'prod' AND node_type = 'model' "
                f"AND node_name = '{model_name}'"
            ),
        )[0][0]
    )


def prod_seed_version_hash(project_dir: Path, seed_name: str) -> str:
    return str(
        query_duckdb(
            db_path=project_dir / "dev_state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_node_refs "
                "WHERE virtual_environment_name = 'prod' AND node_type = 'seed' "
                f"AND node_name = '{seed_name}'"
            ),
        )[0][0]
    )


def dev_version_hash(project_dir: Path, model_name: str) -> str:
    return str(
        query_duckdb(
            db_path=project_dir / "dev_state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_node_refs "
                "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
                f"AND node_name = '{model_name}'"
            ),
        )[0][0]
    )


def dev_ref_rows(project_dir: Path) -> list[tuple[object, ...]]:
    return query_duckdb(
        db_path=project_dir / "dev_state.duckdb",
        sql=(
            "SELECT node_name, version_hash FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'model' ORDER BY node_name"
        ),
    )


def dev_seed_ref_rows(project_dir: Path) -> list[tuple[object, ...]]:
    return query_duckdb(
        db_path=project_dir / "dev_state.duckdb",
        sql=(
            "SELECT node_name, version_hash FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' ORDER BY node_name"
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


def registered_physical_relation_artifacts(project_dir: Path) -> tuple[tuple[str, str], ...]:
    """Read (artifact_type, artifact_name) rows registered in destination state."""

    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "dev_state.duckdb",
        sql=(
            "SELECT artifact_type, artifact_name FROM sqlbuild_state.physical_relations "
            "ORDER BY artifact_type, artifact_name"
        ),
    )
    return tuple((str(row[0]), str(row[1])) for row in rows)
