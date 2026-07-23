from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualSourceFreshnessBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    count_virtual_physical_versions,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="unchanged source freshness skips and changed freshness reruns downstream",
            expected_initial_rows=((7,),),
            expected_updated_rows=((8,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_source_freshness_when_building_then_skips_until_data_version_changes(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: column
                      column: data_version
                      type: integer
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, data_version INTEGER);
            INSERT INTO raw.raw_orders VALUES (7, 1);
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr

    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    unchanged_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert unchanged_build_result.returncode == 0, unchanged_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count

    unchanged_changes_only_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )
    assert unchanged_changes_only_build_result.returncode == 0, (
        unchanged_changes_only_build_result.stderr
    )
    assert "Plan ready (0 selected)" in unchanged_changes_only_build_result.stdout
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count

    explicit_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "fact_orders"),
        project_dir=project_dir,
    )
    assert explicit_build_result.returncode == 0, explicit_build_result.stderr
    assert "fact_orders" in explicit_build_result.stdout
    assert "OK" in explicit_build_result.stdout

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = 2",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="virtual changes-only builds runtime stale table and downstream",
            expected_initial_rows=((7,),),
            expected_updated_rows=((7,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_run_despite_unchanged_when_building_changes_only_then_builds_downstream(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_build_run_despite_unchanged",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: column
                      column: order_ts
                      type: timestamp
                """
            ).strip()
            + "\n",
            "models/rolling_orders.sql": (
                "MODEL (materialized table, run_despite_unchanged 30d);\n\n"
                'SELECT id, order_ts FROM __source("raw_orders")\n'
            ),
            "models/orders_mart.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __ref("rolling_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, order_ts TIMESTAMP);
            INSERT INTO raw.raw_orders VALUES (7, CURRENT_TIMESTAMP);
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.orders_mart ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    changes_only_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )
    assert changes_only_result.returncode == 0, changes_only_result.stderr
    assert "rolling_orders" in changes_only_result.stdout
    assert "orders_mart" in changes_only_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.orders_mart ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="virtual build respects timestamp source freshness lag tolerance",
            expected_initial_rows=((7,),),
            expected_updated_rows=((9,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_timestamp_lag_tolerance_when_building_then_skips_within_tolerance(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_build_lag_tolerance",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: column
                      column: data_version
                      type: timestamp
                      lag_tolerance: 10m
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, data_version TIMESTAMP);
            INSERT INTO raw.raw_orders VALUES (7, '2026-01-01 12:00:00');
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = '2026-01-01 12:05:00'",
    )
    within_tolerance_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert within_tolerance_build_result.returncode == 0, within_tolerance_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 9, data_version = '2026-01-01 12:11:00'",
    )
    beyond_tolerance_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert beyond_tolerance_build_result.returncode == 0, beyond_tolerance_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="unknown source freshness does not skip virtual builds",
            expected_initial_rows=((7,),),
            expected_updated_rows=((8,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_source_without_freshness_when_rebuilding_then_it_does_not_skip(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_unknown_source_freshness_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER);
            INSERT INTO raw.raw_orders VALUES (7);
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8",
    )
    second_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert second_build_result.returncode == 0, second_build_result.stderr
    assert "fact_orders" in second_build_result.stdout
    assert "OK" in second_build_result.stdout
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="source freshness propagates through views to downstream tables",
            expected_initial_rows=((7,),),
            expected_updated_rows=((8,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_source_freshness_through_view_when_changed_then_downstream_table_reruns(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_view_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: column
                      column: data_version
                      type: integer
                """
            ).strip()
            + "\n",
            "models/stg_orders.sql": (
                'MODEL (materialized view);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __ref("stg_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, data_version INTEGER);
            INSERT INTO raw.raw_orders VALUES (7, 1);
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    unchanged_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"), project_dir=project_dir
    )
    assert unchanged_build_result.returncode == 0, unchanged_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = 2",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 2
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="managed loader freshness does not cause spurious virtual rebuilds",
            expected_initial_rows=((7,),),
            expected_updated_rows=((7,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_managed_source_freshness_when_unchanged_then_build_skips_downstream(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_managed_source_freshness_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml().replace(
                "[targets.dev]\n", '[targets.dev]\ndefer_sources_to = "dev"\n'
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('raw_order_id.txt')\n"
                "    return [{'id': int(marker.read_text())}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    (project_dir / "raw_order_id.txt").write_text("7", encoding="utf-8")
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    (project_dir / "raw_order_id.txt").write_text("8", encoding="utf-8")
    unchanged_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"), project_dir=project_dir
    )
    assert unchanged_build_result.returncode == 0, unchanged_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="managed configured freshness conservatively rebinds after first load",
            expected_initial_rows=((7,),),
            expected_updated_rows=((7,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_managed_source_configured_freshness_when_building_then_rebinds_safely(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_managed_configured_source_freshness_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml().replace(
                "[targets.dev]\n", '[targets.dev]\ndefer_sources_to = "dev"\n'
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    root = Path(__file__).parents[1]\n"
                "    return [{\n"
                "        'id': int(root.joinpath('raw_order_id.txt').read_text()),\n"
                "        'data_version': int(root.joinpath('raw_data_version.txt').read_text()),\n"
                "    }]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      query: SELECT MAX(data_version) FROM dev.raw_orders\n"
                "      type: integer\n"
                "    columns:\n"
                "      - name: id\n"
                "        type: INTEGER\n"
                "      - name: data_version\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    (project_dir / "raw_order_id.txt").write_text("7", encoding="utf-8")
    (project_dir / "raw_data_version.txt").write_text("1", encoding="utf-8")
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    rebind_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert rebind_build_result.returncode == 0, rebind_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)

    stable_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert stable_build_result.returncode == 0, stable_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="explicit adapter freshness fails clearly on unsupported adapter",
            expected_initial_rows=(),
            expected_updated_rows=(),
            expected_error_fragment="does not support table freshness metadata",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_adapter_freshness_when_building_then_it_fails_clearly(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_unsupported_adapter_source_freshness_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: adapter
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "CREATE SCHEMA raw; "
            "CREATE TABLE raw.raw_orders (id INTEGER); "
            "INSERT INTO raw.raw_orders VALUES (7);"
        ),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert build_result.returncode == 1
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in (build_result.stdout + build_result.stderr)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="function and source freshness changes independently rerun virtual model",
            expected_initial_rows=((False,),),
            expected_updated_rows=((True,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_source_freshness_and_function_when_each_changes_then_model_reruns(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_function_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: column
                      column: data_version
                      type: integer
                """
            ).strip()
            + "\n",
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change full);\n\n"
                "amount > 9\n"
            ),
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT __udf("is_large_order")(id) AS is_large '
                'FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, data_version INTEGER);
            INSERT INTO raw.raw_orders VALUES (7, 1);
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == list(test_case.expected_initial_rows)

    (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 5\n",
        encoding="utf-8",
    )
    function_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert function_build_result.returncode == 0, function_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == list(test_case.expected_updated_rows)

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 4, data_version = 2",
    )
    source_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert source_build_result.returncode == 0, source_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 2
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == list(test_case.expected_initial_rows)
