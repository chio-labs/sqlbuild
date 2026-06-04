"""E2E tests for sqb build command."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    BuildE2ETestCase,
    DirectChangesOnlyBuildE2ETestCase,
    DirectPythonBuildHardeningE2ETestCase,
    PythonBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    prepare_waffle_shop,
    query_duckdb,
    run_sqb,
    table_exists,
)

DIRECT_PYTHON_BUILD_HARDENING_TEST_CASES: list[DirectPythonBuildHardeningE2ETestCase] = [
    DirectPythonBuildHardeningE2ETestCase(
        description="ingress Python failure blocks downstream source load and model",
        project_name="python_build_ingress_failure_project",
        command=("--no-color", "build", "--select", "+fact_orders"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_build_ingress_failure_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_build_ingress_failure_project.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    raise RuntimeError('prepare failed')\n"
            ),
            "loaders/raw.py": (
                "from tasks.prepare import prepare_orders\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader(depends_on=(prepare_orders,))\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 1}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
        expected_exit_code=1,
        expected_output_fragments=(
            "Python ingress (1)",
            "python    task      prepare_orders",
            "FAIL",
            "Python node failures:",
        ),
        expected_absent_tables=("raw_orders", "fact_orders"),
    ),
    DirectPythonBuildHardeningE2ETestCase(
        description="ingress hard skip blocks downstream source load and model",
        project_name="python_build_ingress_skip_project",
        command=("--no-color", "build", "--select", "+fact_orders"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_build_ingress_skip_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_build_ingress_skip_project.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from sqlbuild.compiler.python_nodes.types import SkipMode\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    return ctx.skip('no input', mode=SkipMode.HARD)\n"
            ),
            "loaders/raw.py": (
                "from tasks.prepare import prepare_orders\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader(depends_on=(prepare_orders,))\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 1}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
        expected_exit_code=0,
        expected_output_fragments=(
            "Python ingress (1)",
            "python    task      prepare_orders",
            "SKIP",
            "no input",
        ),
        expected_absent_tables=("raw_orders", "fact_orders"),
    ),
    DirectPythonBuildHardeningE2ETestCase(
        description="read-side Python failure fails build after SQL succeeds",
        project_name="python_build_read_side_failure_project",
        command=("--no-color", "build", "--select", "fact_orders fail_after_fact"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_build_read_side_failure_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_build_read_side_failure_project.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "tasks/profile.py": (
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def fail_after_fact(ctx):\n"
                "    raise RuntimeError('profile failed')\n"
            ),
        },
        expected_exit_code=1,
        expected_output_fragments=(
            "fact_orders",
            "python    task      fail_after_fact",
            "FAIL",
            "Python node failures:",
        ),
        expected_present_tables=("fact_orders",),
    ),
    DirectPythonBuildHardeningE2ETestCase(
        description="read-side hard skip is reported after SQL succeeds",
        project_name="python_build_read_side_hard_skip_project",
        command=("--no-color", "build", "--select", "fact_orders skip_after_fact"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_build_read_side_hard_skip_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_build_read_side_hard_skip_project.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "tasks/profile.py": (
                "from sqlbuild.compiler.python_nodes.types import SkipMode\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def skip_after_fact(ctx):\n"
                "    return ctx.skip('no profile needed', mode=SkipMode.HARD)\n"
            ),
        },
        expected_exit_code=0,
        expected_output_fragments=(
            "fact_orders",
            "python    task      skip_after_fact",
            "SKIP",
            "no profile needed",
        ),
        expected_present_tables=("fact_orders",),
    ),
    DirectPythonBuildHardeningE2ETestCase(
        description="read-side soft skip is reported after SQL succeeds",
        project_name="python_build_read_side_soft_skip_project",
        command=("--no-color", "build", "--select", "fact_orders soft_skip_after_fact"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_build_read_side_soft_skip_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_build_read_side_soft_skip_project.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "tasks/profile.py": (
                "from sqlbuild.compiler.python_nodes.types import SkipMode\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def soft_skip_after_fact(ctx):\n"
                "    return ctx.skip('optional profile skipped', mode=SkipMode.SOFT)\n"
            ),
        },
        expected_exit_code=0,
        expected_output_fragments=(
            "fact_orders",
            "python    task      soft_skip_after_fact",
            "SKIP",
            "optional profile skipped",
        ),
        expected_present_tables=("fact_orders",),
    ),
    DirectPythonBuildHardeningE2ETestCase(
        description="no-python suppresses read-side Python but keeps ingress Python",
        project_name="python_build_no_python_project",
        command=("--no-color", "build", "--select", "+fact_orders", "--no-python"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_build_no_python_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_build_no_python_project.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from pathlib import Path\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
                "    marker.write_text('prepared')\n"
                "    return ctx.result(payload={'order_id': 3})\n"
            ),
            "loaders/raw.py": (
                "from tasks.prepare import prepare_orders\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader(depends_on=(prepare_orders,))\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 3}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "tasks/profile.py": (
                "from pathlib import Path\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('profile.txt')\n"
                "    marker.write_text('profiled')\n"
                "    return ctx.result()\n"
            ),
        },
        expected_exit_code=0,
        expected_output_fragments=(
            "python    task      prepare_orders",
            "OK",
        ),
        expected_present_tables=("raw_orders", "fact_orders"),
        expected_markers=(("prepared.txt", "prepared"),),
        expected_absent_paths=("profile.txt",),
    ),
    DirectPythonBuildHardeningE2ETestCase(
        description="source relation resolves in direct read-side Python task",
        project_name="python_build_source_relation_project",
        command=("--no-color", "build", "--select", "+raw_orders profile_raw_orders"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_build_source_relation_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_build_source_relation_project.duckdb"\n'
            ),
            "loaders/raw.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 5}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "tasks/profile.py": (
                "from pathlib import Path\n"
                "from sqlbuild.refs import source\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=source('raw_orders'))\n"
                "def profile_raw_orders(ctx):\n"
                "    relation = ctx.relation(source('raw_orders'))\n"
                "    value = ctx.query(f'SELECT order_id FROM {relation}').fetchall()[0][0]\n"
                "    marker = Path(__file__).parents[1].joinpath('source_profile.txt')\n"
                "    marker.write_text(str(value))\n"
                "    return ctx.result(metadata={'source_order_id': value})\n"
            ),
        },
        expected_exit_code=0,
        expected_output_fragments=(
            "python    task      profile_raw_orders",
            "OK",
        ),
        expected_present_tables=("raw_orders",),
        expected_markers=(("source_profile.txt", "5"),),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="direct changes-only build prunes unchanged selected model",
            expected_exit_code=0,
            expected_output_fragments=(
                "Plan ready (0 selected)",
                "Execution  sqb build",
                "Completed successfully.",
                "TOTAL=0",
            ),
            unexpected_output_fragments=("1/1", "orders"),
        )
    ],
    ids=["direct changes-only build prunes unchanged selected model"],
)
def test_given_built_direct_project_when_building_changes_only_then_prunes_unchanged_model(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_build",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_build"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        },
    )
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    output: str = build_result.stdout
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_output_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="direct changes-only build executes changed selected model",
            expected_exit_code=0,
            expected_output_fragments=(
                "Plan ready (1 selected)",
                "Query changed (1)",
                "1/1",
                "orders",
                "TOTAL=1",
            ),
            unexpected_output_fragments=("Plan ready (0 selected)",),
            expected_query_results=((2,),),
        )
    ],
    ids=["direct changes-only build executes changed selected model"],
)
def test_given_direct_query_change_when_building_changes_only_then_executes_changed_model(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changed_changes_only_build",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changed_changes_only_build"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        },
    )
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 2 AS order_id\n",
        encoding="utf-8",
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    output: str = build_result.stdout
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_output_fragments:
        assert fragment not in output, output
    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id FROM orders",
    )
    assert tuple(rows) == test_case.expected_query_results


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="direct changes-only build prunes read-side Python for unchanged SQL",
            expected_exit_code=0,
            expected_output_fragments=(
                "Plan ready (0 selected)",
                "Completed successfully.",
                "TOTAL=0",
            ),
            unexpected_output_fragments=("profile_orders", "Python read-side"),
        )
    ],
    ids=["direct changes-only build prunes read-side Python for unchanged SQL"],
)
def test_given_unchanged_direct_model_when_building_changes_only_then_prunes_read_side_python(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_python_build",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_python_build"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
            "tasks/profile.py": (
                "from pathlib import Path\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('orders'))\n"
                "def profile_orders(ctx):\n"
                "    output = Path(__file__).parents[1].joinpath('profile.txt')\n"
                "    output.write_text('ran')\n"
                "    return ctx.result(metadata={'profiled': True})\n"
            ),
        },
    )
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "orders profile_orders"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )
    marker_path: Path = project_dir / "profile.txt"
    assert marker_path.read_text(encoding="utf-8") == "ran"
    marker_path.unlink()

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only", "--select", "orders profile_orders"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    output: str = build_result.stdout
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_output_fragments:
        assert fragment not in output, output
    assert not marker_path.exists()


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="direct changes-only build observes source freshness without writing state",
            expected_exit_code=0,
            expected_output_fragments=("Plan ready (0 selected)", "TOTAL=0"),
        )
    ],
    ids=["direct changes-only build observes source freshness without writing state"],
)
def test_given_observable_source_freshness_when_building_changes_only_then_does_not_write_state(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_source_freshness_build_read_only",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_source_freshness_build_read_only"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: integer\n"
                "      query: SELECT 1 AS data_version\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
    )
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in build_result.stdout, build_result.stdout
    assert not table_exists(
        db_path=project_dir / "warehouse.duckdb",
        table_name="_sqlbuild_source_freshness",
    )


@pytest.mark.parametrize(
    "test_case",
    DIRECT_PYTHON_BUILD_HARDENING_TEST_CASES,
    ids=[case.description for case in DIRECT_PYTHON_BUILD_HARDENING_TEST_CASES],
)
def test_given_python_lifecycle_edge_case_when_building_then_direct_build_hardens_behavior(
    test_case: DirectPythonBuildHardeningE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / f"{test_case.project_name}.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    combined_output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in combined_output
    table_name: str
    for table_name in test_case.expected_present_tables:
        assert table_exists(db_path=db_path, table_name=table_name)
    for table_name in test_case.expected_absent_tables:
        assert not db_path.exists() or not table_exists(db_path=db_path, table_name=table_name)
    marker_path: str
    expected_marker_text: str
    for marker_path, expected_marker_text in test_case.expected_markers:
        assert (project_dir / marker_path).read_text(encoding="utf-8") == expected_marker_text
    absent_path: str
    for absent_path in test_case.expected_absent_paths:
        assert not (project_dir / absent_path).exists()


DIRECT_SOURCE_ONLY_BUILD_POLICY_TEST_CASES: list[DirectPythonBuildHardeningE2ETestCase] = [
    DirectPythonBuildHardeningE2ETestCase(
        description="direct build fails when skipped intermediate target is missing",
        project_name="direct_build_missing_intermediate_project",
        command=("--no-color", "build", "--select", "raw_events"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_build_missing_intermediate_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "direct_build_missing_intermediate_project.duckdb"\n'
            ),
            "loaders/raw.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    return [{'event_id': 1}]\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                "    ctx.execute_sql(f'CREATE OR REPLACE TABLE {ctx.destination} AS "
                "SELECT event_id FROM {events.destination}')\n"
            ),
            "sources/raw.yml": "sources:\n  - name: raw_events\n    managed: true\n",
        },
        expected_exit_code=1,
        expected_output_fragments=("requires intermediate loader 'fetch_events'",),
    ),
    DirectPythonBuildHardeningE2ETestCase(
        description="direct build no-python source only warns and skips task ingress",
        project_name="direct_build_no_python_source_only_project",
        command=("--no-color", "build", "--select", "raw_events", "--no-python"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_build_no_python_source_only_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "direct_build_no_python_source_only_project.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from pathlib import Path\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_events(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
                "    marker.write_text('prepared')\n"
                "    return ctx.result()\n"
            ),
            "loaders/raw.py": (
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_events\n\n"
                "@loader(depends_on=[prepare_events])\n"
                "def raw_events(ctx):\n"
                "    return [{'event_id': 1}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_events\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
            ),
        },
        expected_exit_code=0,
        expected_output_fragments=("source    raw_events", "unselected upstream task"),
        expected_present_tables=("raw_events",),
        expected_absent_paths=("prepared.txt",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DIRECT_SOURCE_ONLY_BUILD_POLICY_TEST_CASES,
    ids=[case.description for case in DIRECT_SOURCE_ONLY_BUILD_POLICY_TEST_CASES],
)
def test_given_direct_source_only_build_when_loader_has_ingress_then_enforces_source_policy(
    tmp_path: Path,
    test_case: DirectPythonBuildHardeningE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / f"{test_case.project_name}.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    table_name: str
    for table_name in test_case.expected_present_tables:
        assert table_exists(db_path=db_path, table_name=table_name)
    absent_path: str
    for absent_path in test_case.expected_absent_paths:
        assert not (project_dir / absent_path).exists()


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPythonBuildHardeningE2ETestCase(
            description="direct build reuses existing intermediate target without rerunning loader",
            project_name="direct_build_existing_intermediate_project",
            command=("--no-color", "build", "--select", "raw_events"),
            repo_files={
                "sqlbuild_project.toml": (
                    'name = "direct_build_existing_intermediate_project"\n'
                    'adapter = "duckdb"\n\n'
                    "[connection]\n"
                    'database = "direct_build_existing_intermediate_project.duckdb"\n'
                ),
                "loaders/raw.py": (
                    "from sqlbuild.loaders import loader\n\n"
                    "@loader(write_strategy='table', columns=[\n"
                    "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                    "])\n"
                    "def fetch_events(ctx):\n"
                    "    return [{'event_id': 1}]\n\n"
                    "@loader(depends_on=[fetch_events])\n"
                    "def raw_events(ctx):\n"
                    "    events = ctx.loader(fetch_events)\n"
                    "    ctx.execute_sql(f'CREATE OR REPLACE TABLE {ctx.destination} AS "
                    "SELECT event_id FROM {events.destination}')\n"
                ),
                "sources/raw.yml": "sources:\n  - name: raw_events\n    managed: true\n",
            },
            expected_exit_code=0,
            expected_output_fragments=("source    raw_events",),
            expected_present_tables=("raw_events",),
        )
    ],
    ids=["direct build reuses existing intermediate target without rerunning loader"],
)
def test_given_existing_intermediate_target_when_building_source_only_then_reuses_target(
    tmp_path: Path,
    test_case: DirectPythonBuildHardeningE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files=test_case.repo_files,
    )
    setup_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "load", "--select", "fetch_events"),
        project_dir=project_dir,
    )
    assert setup_result.returncode == 0, setup_result.stdout + setup_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert "loader    fetch_events" not in result.stdout
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in result.stdout
    db_path: Path = project_dir / f"{test_case.project_name}.duckdb"
    table_name: str
    for table_name in test_case.expected_present_tables:
        assert table_exists(db_path=db_path, table_name=table_name)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPythonBuildHardeningE2ETestCase(
            description="build json includes Python node results",
            project_name="python_build_json_project",
            command=("--no-color", "build", "--select", "observed_orders"),
            repo_files={
                "sqlbuild_project.toml": (
                    'name = "python_build_json_project"\n'
                    'adapter = "duckdb"\n\n'
                    "[connection]\n"
                    'database = "python_build_json_project.duckdb"\n'
                ),
                "assets/orders.py": (
                    "from sqlbuild.assets import asset\n\n"
                    "@asset\n"
                    "def observed_orders(ctx):\n"
                    "    return ctx.result(metadata={'uri': 's3://orders'}, materialized=False)\n"
                ),
            },
            expected_exit_code=0,
            expected_output_fragments=("python    asset     observed_orders", "OK"),
            expected_json_assets=(("observed_orders", "success"),),
            expected_json_status="success",
        )
    ],
    ids=["build json includes Python node results"],
)
def test_given_python_asset_with_json_output_when_building_then_json_includes_python_result(
    test_case: DirectPythonBuildHardeningE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files=test_case.repo_files,
    )
    json_output_path: Path = project_dir / "target" / "build.json"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "build",
            "--json-output",
            str(json_output_path),
            "--select",
            "observed_orders",
        ),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in result.stdout
    payload: dict[str, object] = json.loads(json_output_path.read_text(encoding="utf-8"))
    assert payload["status"] == test_case.expected_json_status
    assets: dict[str, dict[str, object]] = {
        str(asset["name"]): asset
        for asset in payload["assets"]  # type: ignore[index]
    }
    asset_name: str
    expected_status: str
    for asset_name, expected_status in test_case.expected_json_assets:
        assert assets[asset_name]["status"] == expected_status
    assert assets["observed_orders"]["kind"] == "asset"
    assert assets["observed_orders"]["metadata"] == {"uri": "s3://orders"}
    assert assets["observed_orders"]["materialized"] is False
    assert payload["summary"] == {
        "success_count": 1,
        "failure_count": 0,
        "skipped_count": 0,
        "warning_count": 0,
        "python_check_pass_count": 0,
        "python_check_warn_count": 0,
        "python_check_fail_count": 0,
    }


@pytest.mark.parametrize(
    "test_case",
    [
        PythonBuildE2ETestCase(
            description="build executes full Python SQL Python spine in lifecycle order",
            expected_exit_code=0,
            expected_execution_fragments=(
                "Python ingress (2)",
                "Python read-side (3)",
                "python    task      prepare_orders",
                "python    asset     publish_prepared_orders",
                "python    task      profile_fact_orders",
                "python    asset     export_fact_orders",
                "python    task      notify_fact_orders",
            ),
            expected_table_names=("window_orders", "raw_orders", "fact_orders"),
            expected_notify_text="7",
            expected_fact_orders_rows=((7,),),
        )
    ],
    ids=["build executes full Python SQL Python spine in lifecycle order"],
)
def test_given_python_sql_python_spine_when_building_then_orders_python_around_sql(
    test_case: PythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_sql_python_spine_build_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_sql_python_spine_build_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_sql_python_spine_build_project.duckdb"\n'
            ),
            "loaders/window.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader(\n"
                "    destination='window_orders',\n"
                "    write_strategy='table',\n"
                "    columns=[{'name': 'order_id', 'type': 'INTEGER'}],\n"
                ")\n"
                "def load_window_orders(ctx):\n"
                "    return [{'order_id': 7}]\n"
            ),
            "tasks/prepare.py": (
                "from loaders.window import load_window_orders\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=load_window_orders)\n"
                "def prepare_orders(ctx):\n"
                "    rows = ctx.query('SELECT order_id FROM window_orders').fetchall()\n"
                "    return ctx.result(payload={'order_id': rows[0][0]})\n"
            ),
            "assets/prepare.py": (
                "from pathlib import Path\n"
                "from tasks.prepare import prepare_orders\n"
                "from sqlbuild.assets import asset\n\n"
                "@asset(depends_on=prepare_orders)\n"
                "def publish_prepared_orders(ctx):\n"
                "    payload = ctx.payload(prepare_orders)\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared_order_id.txt')\n"
                "    marker.write_text(str(payload['order_id']))\n"
                "    return ctx.result(payload=payload, materialized=True)\n"
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from assets.prepare import publish_prepared_orders\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader(depends_on=(publish_prepared_orders,))\n"
                "def raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared_order_id.txt')\n"
                "    return [{'order_id': int(marker.read_text())}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "tasks/profile.py": (
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    relation = ctx.relation(model('fact_orders'))\n"
                "    order_id = ctx.query(f'SELECT order_id FROM {relation}').fetchall()[0][0]\n"
                "    return ctx.result(payload={'order_id': order_id}, metadata={'rows': 1})\n"
            ),
            "assets/export.py": (
                "from tasks.profile import profile_fact_orders\n"
                "from sqlbuild.assets import asset\n\n"
                "@asset(depends_on=profile_fact_orders)\n"
                "def export_fact_orders(ctx):\n"
                "    payload = ctx.payload(profile_fact_orders)\n"
                "    return ctx.result(payload=payload, metadata={'exported': True})\n"
            ),
            "tasks/notify.py": (
                "from pathlib import Path\n"
                "from assets.export import export_fact_orders\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=export_fact_orders)\n"
                "def notify_fact_orders(ctx):\n"
                "    payload = ctx.payload(export_fact_orders)\n"
                "    output = Path(__file__).parents[1].joinpath('notify.txt')\n"
                "    output.write_text(str(payload['order_id']))\n"
                "    return ctx.result(metadata={'notified': True})\n"
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders +notify_fact_orders"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_execution_fragments:
        assert fragment in result.stdout
    execution_output: str = result.stdout[result.stdout.index("Execution  sqb build") :]
    assert execution_output.index("window_orders") < execution_output.index("prepare_orders")
    assert execution_output.index("prepare_orders") < execution_output.index(
        "publish_prepared_orders"
    )
    assert execution_output.index("raw_orders") < execution_output.index("fact_orders")
    assert execution_output.index("fact_orders") < execution_output.index("profile_fact_orders")
    assert execution_output.index("profile_fact_orders") < execution_output.index(
        "export_fact_orders"
    )
    assert execution_output.index("export_fact_orders") < execution_output.index(
        "notify_fact_orders"
    )
    assert (project_dir / "notify.txt").read_text(encoding="utf-8") == (
        test_case.expected_notify_text
    )
    db_path: Path = project_dir / "python_sql_python_spine_build_project.duckdb"
    table_name: str
    for table_name in test_case.expected_table_names:
        assert table_exists(db_path=db_path, table_name=table_name)
    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT order_id FROM fact_orders",
    )
    assert tuple(rows) == test_case.expected_fact_orders_rows


@pytest.mark.parametrize(
    "test_case",
    [
        BuildE2ETestCase(
            description="build materializes all tables views and seeds with correct data",
            expected_exit_code=0,
            expected_table_names=(
                "daily_order_partitioned",
                "daily_revenue",
                "dim_customers",
                "fact_orders",
            ),
            expected_view_names=("stg_customers", "stg_orders", "stg_payments"),
            expected_seed_names=("waffle_types",),
            expected_fact_orders_data=(
                (1, 1, "Classic Belgian", "completed"),
                (2, 1, "Cheddar Herb", "completed"),
                (3, 2, "Chicken and Waffle", "completed"),
                (4, 3, "Liege", "completed"),
                (5, 4, "Classic Belgian", "completed"),
                (6, 4, "Brussels", "completed"),
                (7, 5, "Everything Bagel", "cancelled"),
                (8, 1, "Liege", "completed"),
                (9, 2, "Chicken and Waffle", "preparing"),
                (10, 3, "Classic Belgian", "placed"),
            ),
            expected_fact_orders_python_udf_data=((1, True), (10, False)),
            expected_customer_orders_table_function_data=(
                (1, "Classic Belgian", 1700, "completed", True),
                (2, "Cheddar Herb", 1050, "completed", True),
                (8, "Liege", 950, "completed", True),
            ),
            expected_dim_customers_data=(
                (1, "Leslie", 3, 3700),
                (2, "Ron", 2, 4350),
                (3, "Ann", 2, 950),
                (4, "Ben", 2, 1600),
                (5, "April", 1, 0),
            ),
            expected_waffle_types_data=(
                (1, "Classic Belgian", "sweet", 850),
                (2, "Liege", "sweet", 950),
                (3, "Brussels", "sweet", 750),
                (4, "Cheddar Herb", "savory", 1050),
                (5, "Everything Bagel", "savory", 1100),
                (6, "Chicken and Waffle", "savory", 1450),
            ),
            expected_daily_revenue_data=(
                ("2026-04-01", 3, 6, 7100),
                ("2026-04-02", 3, 3, 2550),
                ("2026-04-03", 1, 1, 950),
            ),
            expected_daily_order_partitioned_data=(
                ("2026-04-01", 3, 6, 2),
                ("2026-04-02", 3, 3, 2),
                ("2026-04-03", 2, 3, 2),
                ("2026-04-04", 2, 6, 2),
            ),
        ),
    ],
    ids=["build materializes all tables views and seeds with correct data"],
)
def test_given_waffle_shop_project_when_running_build_then_warehouse_state_matches_expected(
    test_case: BuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    db_path: Path = project_dir / "waffle_shop.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    run_sql_path: Path = project_dir / "target" / "run" / "models" / "marts" / "fact_orders.sql"
    assert run_sql_path.exists()
    run_sql: str = run_sql_path.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE TABLE main.fact_orders__staging AS" in run_sql
    assert "ALTER TABLE main.fact_orders__staging RENAME TO fact_orders;" in run_sql

    table_name: str
    for table_name in test_case.expected_table_names:
        assert table_exists(db_path=db_path, table_name=table_name), (
            f"table {table_name} should exist"
        )

    view_name: str
    for view_name in test_case.expected_view_names:
        assert table_exists(db_path=db_path, table_name=view_name), f"view {view_name} should exist"

    seed_name: str
    for seed_name in test_case.expected_seed_names:
        assert table_exists(db_path=db_path, table_name=seed_name), f"seed {seed_name} should exist"

    fact_sql: str = (
        "SELECT order_id, customer_id, waffle_name, order_status "
        "FROM main.fact_orders ORDER BY order_id"
    )
    fact_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=fact_sql)
    assert tuple(tuple(r) for r in fact_rows) == test_case.expected_fact_orders_data

    python_udf_sql: str = (
        "SELECT order_id, is_completed_order_py FROM main.fact_orders "
        "WHERE order_id IN (1, 10) ORDER BY order_id"
    )
    python_udf_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=python_udf_sql)
    assert (
        tuple(tuple(r) for r in python_udf_rows) == test_case.expected_fact_orders_python_udf_data
    )

    table_function_sql: str = (
        "SELECT order_id, waffle_name, line_total_cents, order_status, is_completed_order "
        "FROM main.customer_orders(1) ORDER BY order_id"
    )
    table_function_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path, sql=table_function_sql
    )
    assert (
        tuple(tuple(r) for r in table_function_rows)
        == test_case.expected_customer_orders_table_function_data
    )

    dim_sql: str = (
        "SELECT customer_id, first_name, lifetime_orders, lifetime_spend_cents "
        "FROM main.dim_customers ORDER BY customer_id"
    )
    dim_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=dim_sql)
    assert tuple(tuple(r) for r in dim_rows) == test_case.expected_dim_customers_data

    seed_sql: str = (
        "SELECT waffle_type_id, waffle_name, category, price_cents "
        "FROM main.waffle_types ORDER BY waffle_type_id"
    )
    seed_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=seed_sql)
    assert tuple(tuple(r) for r in seed_rows) == test_case.expected_waffle_types_data

    revenue_sql: str = (
        "SELECT CAST(revenue_date AS VARCHAR), order_count, "
        "waffles_sold, total_revenue_cents "
        "FROM main.daily_revenue ORDER BY revenue_date"
    )
    revenue_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=revenue_sql)
    assert tuple(tuple(r) for r in revenue_rows) == test_case.expected_daily_revenue_data

    partitioned_sql: str = (
        "SELECT CAST(order_date AS VARCHAR), order_count, "
        "waffles_ordered, unique_customers "
        "FROM main.daily_order_partitioned ORDER BY order_date"
    )
    partitioned_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=partitioned_sql)
    assert (
        tuple(tuple(r) for r in partitioned_rows) == test_case.expected_daily_order_partitioned_data
    )
