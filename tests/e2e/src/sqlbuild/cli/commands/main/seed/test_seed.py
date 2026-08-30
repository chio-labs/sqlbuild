"""E2E tests for sqb seed command."""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
)
from tests.e2e.src.sqlbuild.cli.commands.main.seed._test_types import (
    SeedE2ETestCase,
    VirtualSeedE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    prepare_waffle_shop,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SeedE2ETestCase(
            description="seed loads waffle_types CSV with correct data",
            expected_exit_code=0,
            expected_seed_name="waffle_types",
            expected_data=(
                (1, "Classic Belgian", "sweet", 850),
                (2, "Liege", "sweet", 950),
                (3, "Brussels", "sweet", 750),
                (4, "Cheddar Herb", "savory", 1050),
                (5, "Everything Bagel", "savory", 1100),
                (6, "Chicken and Waffle", "savory", 1450),
            ),
            expected_stdout_fragments=(
                "Seed ready  1 selected",
                "Seeds (1)",
                "waffle_types",
                "Execution  sqb seed  (concurrency:",
                "1/1  seed      waffle_types",
                "\u2713 Completed successfully",
                "PASS=1  WARN=0  FAIL=0  SKIP=0  TOTAL=1",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_waffle_shop_project_when_running_seed_then_seed_data_matches_expected(
    test_case: SeedE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    db_path: Path = project_dir / "waffle_shop.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "seed"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert all(fragment in result.stdout for fragment in test_case.expected_stdout_fragments)
    assert table_exists(db_path=db_path, table_name=test_case.expected_seed_name)

    seed_sql: str = (
        "SELECT waffle_type_id, waffle_name, category, price_cents "
        f"FROM main.{test_case.expected_seed_name} ORDER BY waffle_type_id"
    )
    rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=seed_sql)
    assert tuple(tuple(r) for r in rows) == test_case.expected_data


@pytest.mark.parametrize(
    "test_case",
    [
        SeedE2ETestCase(
            description="empty typed seed fields load as null",
            expected_exit_code=0,
            expected_seed_name="nullable_mappings",
            expected_data=((1, "mapped"), (None, None)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_empty_typed_seed_fields_when_loading_then_persists_nulls(
    test_case: SeedE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="nullable_seed_fields",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "nullable_seed_fields"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[targets.dev]\n"
                'schema = "main"\n'
                "[targets.dev.connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "seeds/schema.yml": (
                "seeds:\n"
                "  - name: nullable_mappings\n"
                "    columns:\n"
                "      - name: mapping_id\n"
                "        type: INTEGER\n"
                "      - name: mapping_name\n"
                "        type: VARCHAR\n"
            ),
            "seeds/nullable_mappings.csv": "mapping_id,mapping_name\n1,mapped\n,\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "seed"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=f"SELECT mapping_id, mapping_name FROM main.{test_case.expected_seed_name} ORDER BY mapping_id",
    )
    assert tuple(tuple(row) for row in rows) == test_case.expected_data


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedE2ETestCase(
            description="virtual seed command persists VDE seed state",
            expected_seed_rows=((1, 100),),
            expected_seed_fragments=(
                "Plan ready  1 selected",
                "order_amounts",
                "Execution  sqb seed  (concurrency:",
                "\u2713 Completed successfully",
            ),
            expected_current_seed_fragments=(
                "Plan ready  1 selected",
                "order_amounts  (current)",
            ),
            expected_build_fragments=("Plan ready  1 selected", "fact_orders"),
            unexpected_build_fragments=("order_amounts",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_project_when_running_seed_then_persists_seed_state(
    test_case: VirtualSeedE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_command",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "seeds/schema.yml": (
                "seeds:\n"
                "  - name: order_amounts\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: amount_cents\n"
                "        type: INTEGER\n"
            ),
            "seeds/order_amounts.csv": "order_id,amount_cents\n1,100\n",
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __seed("order_amounts")\n'
            ),
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr

    seed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "seed"),
        project_dir=project_dir,
    )

    assert seed_result.returncode == 0, seed_result.stdout + seed_result.stderr
    fragment: str
    for fragment in test_case.expected_seed_fragments:
        assert fragment in seed_result.stdout, seed_result.stdout
    seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' ORDER BY node_name"
        ),
    )
    assert seed_ref_rows == [("order_amounts",)]
    seed_physical_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT artifact_type, artifact_name, schema_name, relation_name "
            "FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'seed' AND artifact_name = 'order_amounts'"
        ),
    )
    assert len(seed_physical_rows) == 1
    assert seed_physical_rows[0][0:2] == ("seed", "order_amounts")
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.order_amounts ORDER BY order_id",
    ) == list(test_case.expected_seed_rows)

    current_seed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "seed", "--select", "order_amounts"),
        project_dir=project_dir,
    )
    assert current_seed_result.returncode == 0, (
        current_seed_result.stdout + current_seed_result.stderr
    )
    for fragment in test_case.expected_current_seed_fragments:
        assert fragment in current_seed_result.stdout, current_seed_result.stdout

    json_seed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("seed", "--select", "order_amounts", "--json"),
        project_dir=project_dir,
    )
    assert json_seed_result.returncode == 0, json_seed_result.stderr
    json_payload: dict[str, object] = json.loads(json_seed_result.stdout)
    assert json_payload["command"] == test_case.expected_json_command
    assets_by_kind: defaultdict[object, list[dict[str, object]]] = defaultdict(list)
    for asset in json_payload["assets"]:
        typed_asset: dict[str, object] = dict(asset)
        assets_by_kind[typed_asset.get("kind")].append(typed_asset)
    seed_assets: list[dict[str, object]] = assets_by_kind["seed"]
    assert len(seed_assets) == 1
    assert seed_assets[0]["name"] == "order_amounts"
    assert seed_assets[0]["reason"] == test_case.expected_json_reason

    physical_schema_name, physical_relation_name = seed_physical_rows[0][2:4]
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=f'DROP TABLE "{physical_schema_name}"."{physical_relation_name}"',
    )
    reload_seed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "seed", "--select", "order_amounts"),
        project_dir=project_dir,
    )
    assert reload_seed_result.returncode == 0, reload_seed_result.stdout + reload_seed_result.stderr
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.order_amounts ORDER BY order_id",
    ) == list(test_case.expected_seed_rows)

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    for fragment in test_case.expected_build_fragments:
        assert fragment in build_result.stdout, build_result.stdout
    for fragment in test_case.unexpected_build_fragments:
        assert fragment not in build_result.stdout, build_result.stdout
