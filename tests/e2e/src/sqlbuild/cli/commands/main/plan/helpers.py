"""Project builders for plan command e2e tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.main.lineage.helpers import DIAMOND_LAYERS
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    run_sqb,
)

DIAMOND_DATABASE_FILE: str = "orders.duckdb"
_DIAMOND_PROJECT_TOML: str = (
    'name = "incremental_diamond"\nadapter = "duckdb"\n\n'
    f'[connection]\ndatabase = "{DIAMOND_DATABASE_FILE}"\n'
)
_DIAMOND_SOURCES_YML: str = (
    "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
)
_DIAMOND_ROOT_PATH: str = "models/orders_0.sql"


def _incremental_header(*, extra_config: str) -> str:
    return (
        "MODEL (\n"
        "  materialized incremental,\n"
        "  incremental_strategy delete_insert,\n"
        "  unique_key order_id,\n"
        "  cursor order_date,\n"
        "  cursor_type timestamp,\n"
        "  cursor_grain day,\n"
        '  cursor_start "2026-01-01",\n'
        f"{extra_config}"
        ");\n\n"
    )


def _diamond_root_sql(*, amount_offset: int) -> str:
    return (
        _incremental_header(extra_config="  replay_on_change full,\n")
        + "SELECT order_id, order_date, amount_cents + "
        f'{amount_offset} AS amount_cents FROM __source("raw_orders")\n'
    )


def prepare_incremental_diamond_project(*, tmp_path: Path) -> Path:
    """Write incremental layered diamonds whose root replays fully on change."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": _DIAMOND_PROJECT_TOML,
        "sources/raw.yml": _DIAMOND_SOURCES_YML,
        _DIAMOND_ROOT_PATH: _diamond_root_sql(amount_offset=0),
    }
    for layer in range(1, DIAMOND_LAYERS + 1):
        for side in ("left", "right"):
            files[f"models/orders_{side}_{layer}.sql"] = (
                _incremental_header(extra_config="") + "SELECT order_id, order_date, amount_cents "
                f'FROM __ref("orders_{layer - 1}")\n'
            )
        files[f"models/orders_{layer}.sql"] = (
            _incremental_header(
                extra_config=(
                    f"  cursor_inputs (orders_left_{layer} order_date, "
                    f"orders_right_{layer} order_date,),\n"
                )
            )
            + "SELECT l.order_id, l.order_date, l.amount_cents + r.amount_cents AS amount_cents\n"
            f'FROM __ref("orders_left_{layer}") AS l\n'
            f'JOIN __ref("orders_right_{layer}") AS r ON l.order_id = r.order_id\n'
        )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="incremental_diamond", repo_files=files
    )
    execute_duckdb(
        db_path=project_dir / DIAMOND_DATABASE_FILE,
        sql=(
            "CREATE TABLE main.raw_orders AS SELECT i AS order_id, "
            "TIMESTAMP '2026-01-01' + to_days(CAST(i - 1 AS INTEGER)) AS order_date, "
            "100 + i AS amount_cents FROM range(1, 4) AS t(i)"
        ),
    )
    return project_dir


def change_incremental_diamond_root(*, project_dir: Path) -> None:
    """Change the root query so every downstream model inherits a full replay."""

    (project_dir / _DIAMOND_ROOT_PATH).write_text(
        _diamond_root_sql(amount_offset=1), encoding="utf-8"
    )


def prepare_changed_incremental_diamond_project(*, tmp_path: Path) -> Path:
    """Build the incremental diamonds, then change the root so the plan cascades."""

    project_dir: Path = prepare_incremental_diamond_project(tmp_path=tmp_path)
    build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build.returncode == 0, build.stdout + build.stderr
    change_incremental_diamond_root(project_dir=project_dir)
    return project_dir
