from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualSeedBuildE2ETestCase,
    VirtualSeedGapE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedBuildE2ETestCase(
            description="virtual seed build persists seed refs and reloads changed seeds",
            expected_initial_rows=((1, 100),),
            expected_changed_rows=((1, 200),),
            expected_changed_fragments=(
                "order_amounts",
                "seed_changed",
                "fact_orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_seed_change_when_building_changes_only_then_updates_seed_state_and_model(
    test_case: VirtualSeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_change_build",
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
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_initial_rows)
    initial_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    assert len(initial_seed_ref_rows) == 1

    default_unchanged_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_unchanged_build_result.returncode == 0, default_unchanged_build_result.stderr
    assert "order_amounts" in default_unchanged_build_result.stdout
    assert "fact_orders" in default_unchanged_build_result.stdout
    assert "OK" in default_unchanged_build_result.stdout
    assert "seed      order_amounts" in default_unchanged_build_result.stdout
    assert "SKIP=0" in default_unchanged_build_result.stdout

    unchanged_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )
    assert unchanged_build_result.returncode == 0, unchanged_build_result.stderr
    assert "Plan ready (0 selected)" in unchanged_build_result.stdout

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n",
        encoding="utf-8",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, (
        changed_build_result.stdout + changed_build_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_changed_fragments:
        assert fragment in changed_build_result.stdout, changed_build_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)
    changed_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    assert len(changed_seed_ref_rows) == 1
    assert changed_seed_ref_rows[0][0] == "order_amounts"
    assert changed_seed_ref_rows[0][1] != initial_seed_ref_rows[0][1]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedBuildE2ETestCase(
            description="two VDEs bind isolated seed physical versions",
            expected_initial_rows=((1, 100),),
            expected_changed_rows=((1, 100),),
            expected_branch_rows=((1, 200),),
            expected_changed_fragments=(),
            expected_physical_seed_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_two_virtual_environments_when_seed_differs_then_each_reads_bound_seed_version(
    test_case: VirtualSeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_isolation",
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
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    dev_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert dev_build_result.returncode == 0, dev_build_result.stdout + dev_build_result.stderr

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n",
        encoding="utf-8",
    )
    pr_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert pr_build_result.returncode == 0, pr_build_result.stdout + pr_build_result.stderr

    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__pr.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_branch_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.order_amounts ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__pr.order_amounts ORDER BY order_id",
    ) == list(test_case.expected_branch_rows)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT COUNT(*) FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'seed' AND artifact_name = 'order_amounts'"
        ),
    ) == [(test_case.expected_physical_seed_count,)]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedBuildE2ETestCase(
            description="second VDE reuses existing physical seed artifact",
            expected_initial_rows=((1, 100),),
            expected_changed_rows=((1, 100),),
            expected_changed_fragments=("order_amounts",),
            expected_physical_seed_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_second_vde_when_seed_version_exists_then_uses_existing_physical_seed(
    test_case: VirtualSeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_existing_artifact",
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
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    pr_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )

    assert pr_build_result.returncode == 0, pr_build_result.stdout + pr_build_result.stderr
    for fragment in test_case.expected_changed_fragments:
        assert fragment in pr_build_result.stdout, pr_build_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__pr.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__pr.order_amounts ORDER BY order_id",
    ) == list(test_case.expected_initial_rows)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT COUNT(*) FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'seed' AND artifact_name = 'order_amounts'"
        ),
    ) == [(test_case.expected_physical_seed_count,)]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedBuildE2ETestCase(
            description="explicit model selection updates stale upstream seed artifact",
            expected_initial_rows=((1, 100),),
            expected_changed_rows=((1, 200),),
            expected_changed_fragments=("order_amounts", "fact_orders"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_model_selection_when_upstream_seed_changed_then_model_reads_new_seed(
    test_case: VirtualSeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_explicit_model_with_changed_seed",
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
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_initial_rows)

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n",
        encoding="utf-8",
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "fact_orders"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    for fragment in test_case.expected_changed_fragments:
        assert fragment in build_result.stdout, build_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="failed virtual seed reload leaves seed ref unchanged",
            expected_fragments=("order_amounts", "FAIL", "Completed with errors."),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_seed_load_failure_when_building_changes_only_then_seed_state_is_unchanged(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_failure_build",
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
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )
    initial_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' ORDER BY node_name"
        ),
    )

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,not_an_integer\n",
        encoding="utf-8",
    )
    failed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert failed_build_result.returncode == 1, (
        failed_build_result.stdout + failed_build_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in failed_build_result.stdout, failed_build_result.stdout
    assert (
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT node_name, version_hash FROM sqlbuild_state.virtual_environment_node_refs "
                "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
                "ORDER BY node_name"
            ),
        )
        == initial_seed_ref_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="virtual seed JSON includes seed reasons",
            expected_fragments=("order_amounts", "config_changed"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_seed_change_when_plan_and_build_json_then_seed_reason_is_reported(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_json_build",
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
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n", encoding="utf-8"
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--json"), project_dir=project_dir
    )
    assert plan_result.returncode == 0, plan_result.stderr
    plan_payload: dict[str, object] = json.loads(plan_result.stdout)
    plan_seeds: list[dict[str, object]] = list(plan_payload["seeds"])
    expected_seed_name, expected_seed_reason = test_case.expected_fragments
    physical_seed_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT schema_name, relation_name FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'seed' AND artifact_name = 'order_amounts'"
        ),
    )
    assert len(physical_seed_rows) == 1
    physical_schema, physical_name = physical_seed_rows[0]
    assert len(plan_seeds) == 1
    planned_seed: dict[str, object] = plan_seeds[0]
    assert planned_seed["name"] == expected_seed_name
    assert planned_seed["reason"] == expected_seed_reason
    planned_qualified_name: object = planned_seed["qualified_name"]
    assert isinstance(planned_qualified_name, str)
    assert planned_qualified_name.startswith(f"{physical_schema}.{expected_seed_name}__v_")
    assert planned_qualified_name != f"{physical_schema}.{physical_name}"

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("build", "--json"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stderr
    build_payload: dict[str, object] = json.loads(build_result.stdout)
    assets_by_kind: defaultdict[object, list[dict[str, object]]] = defaultdict(list)
    for asset in build_payload["assets"]:
        typed_asset: dict[str, object] = dict(asset)
        assets_by_kind[typed_asset.get("kind")].append(typed_asset)
    seed_assets: list[dict[str, object]] = assets_by_kind["seed"]
    assert len(seed_assets) == 1
    assert seed_assets[0]["name"] == expected_seed_name
    assert seed_assets[0]["reason"] == expected_seed_reason


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="virtual seed schema change reloads seed and model",
            expected_fragments=(
                "Plan ready (2 selected)",
                "order_amounts",
                "seed_changed",
                "fact_orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_seed_schema_change_when_building_changes_only_then_reloads_seed_and_model(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_schema_change_build",
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
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "schema.yml").write_text(
        "seeds:\n"
        "  - name: order_amounts\n"
        "    columns:\n"
        "      - name: order_id\n"
        "        type: INTEGER\n"
        "      - name: amount_cents\n"
        "        type: BIGINT\n",
        encoding="utf-8",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="multi seed virtual graph selects only changed seed closure",
            expected_fragments=("Plan ready (2 selected)", "order_amounts", "fact_orders"),
            unexpected_fragments=("country_codes", "dim_countries"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multi_seed_graph_when_one_seed_changes_then_only_its_closure_is_selected(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_multi_seed_change_build",
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
                "  - name: country_codes\n"
                "    columns:\n"
                "      - name: country_code\n"
                "        type: TEXT\n"
            ),
            "seeds/order_amounts.csv": "order_id,amount_cents\n1,100\n",
            "seeds/country_codes.csv": "country_code\nUS\n",
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __seed("order_amounts")\n'
            ),
            "models/dim_countries.sql": (
                'MODEL (materialized table);\n\nSELECT country_code FROM __seed("country_codes")\n'
            ),
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n", encoding="utf-8"
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="virtual model change with current seed does not reload seed",
            expected_fragments=("Plan ready (1 selected)", "fact_orders"),
            unexpected_fragments=("Seeds (", "seed      order_amounts"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_change_with_current_seed_when_building_then_seed_is_not_reloaded(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_model_change_current_seed_build",
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
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "fact_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        "SELECT order_id, amount_cents, amount_cents / 100.0 AS amount_dollars "
        'FROM __seed("order_amounts")\n',
        encoding="utf-8",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result.stdout, result.stdout
