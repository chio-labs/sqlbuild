"""E2E tests for sqb build command."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    BuildE2ETestCase,
    DeferCloneBuildE2ETestCase,
    DependencyBaselineBuildE2ETestCase,
    DirectChangesOnlyBuildE2ETestCase,
    PythonBuildE2ETestCase,
    PythonLoaderPersistedResultBuildE2ETestCase,
    PythonLoaderStatusResultBuildE2ETestCase,
    PythonPersistedResultBuildE2ETestCase,
    PythonTargetIsolationBuildE2ETestCase,
    SelectionAwareStalenessBuildE2ETestCase,
    StandardPythonBuildHardeningE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    assert_defer_clone_build_case,
    assert_dependency_baseline_build_case,
    build_freshness_error_branch_source_yml,
    downstream_model_sql,
    incremental_upstream_model_sql,
    raw_orders_setup_sql,
    table_upstream_model_sql,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    prepare_waffle_shop,
    query_duckdb,
    run_sqb,
    table_exists,
)

DEPENDENCY_BASELINE_TEST_CASES: list[DependencyBaselineBuildE2ETestCase] = [
    DependencyBaselineBuildE2ETestCase(
        description="missing table upstream is baselined before downstream build",
        project_name="dependency_baseline_missing_table",
        upstream_sql=table_upstream_model_sql(amount=100),
        downstream_sql=downstream_model_sql(),
        prod_setup_sql=raw_orders_setup_sql(rows_sql="(1, 100, TIMESTAMP '2026-01-01 00:00:00')"),
        setup_commands=(("--no-color", "build", "--target", "prod", "--select", "upstream"),),
        command=("--no-color", "build", "--select", "downstream"),
        expected_stdout_fragments=(
            "Plan ready (1 selected)",
            "Reused inputs (1)",
            "upstream",
            "from reuse origin target",
            "downstream",
            "Completed successfully.",
        ),
        unexpected_stdout_fragments=("cannot build selected scope",),
        expected_upstream_rows=((1, 100),),
        expected_downstream_rows=((1, 100),),
        expected_fingerprint_rows=(("model", "downstream"),),
    ),
    DependencyBaselineBuildE2ETestCase(
        description="current table upstream does not baseline",
        project_name="dependency_baseline_current_table",
        upstream_sql=table_upstream_model_sql(amount=110),
        downstream_sql=downstream_model_sql(),
        prod_setup_sql=raw_orders_setup_sql(rows_sql="(1, 110, TIMESTAMP '2026-01-01 00:00:00')"),
        setup_commands=(
            ("--no-color", "build", "--target", "prod", "--select", "upstream"),
            ("--no-color", "build", "--target", "dev", "--select", "upstream"),
        ),
        command=("--no-color", "build", "--select", "downstream"),
        expected_stdout_fragments=("Plan ready (1 selected)", "downstream"),
        unexpected_stdout_fragments=("Reused inputs",),
        expected_upstream_rows=((1, 110),),
        expected_downstream_rows=((1, 110),),
        expected_fingerprint_rows=(("model", "downstream"), ("model", "upstream")),
    ),
    DependencyBaselineBuildE2ETestCase(
        description="stale table upstream is baselined before downstream build",
        project_name="dependency_baseline_stale_table",
        upstream_sql=table_upstream_model_sql(amount=120),
        downstream_sql=downstream_model_sql(),
        prod_setup_sql=raw_orders_setup_sql(rows_sql="(1, 120, TIMESTAMP '2026-01-01 00:00:00')"),
        dev_setup_sql=(
            "CREATE SCHEMA dev;\nCREATE TABLE dev.upstream AS SELECT 1 AS id, 999 AS amount;\n"
        ),
        setup_commands=(("--no-color", "build", "--target", "prod", "--select", "upstream"),),
        command=("--no-color", "build", "--select", "downstream"),
        expected_stdout_fragments=("Reused inputs (1)", "from reuse origin target"),
        unexpected_stdout_fragments=("cannot build selected scope",),
        expected_upstream_rows=((1, 120),),
        expected_downstream_rows=((1, 120),),
        expected_fingerprint_rows=(("model", "downstream"),),
    ),
    DependencyBaselineBuildE2ETestCase(
        description="incremental upstream baselines whole relation without catch-up",
        project_name="dependency_baseline_incremental_whole_relation",
        upstream_sql=incremental_upstream_model_sql(),
        downstream_sql=downstream_model_sql(),
        prod_setup_sql=raw_orders_setup_sql(rows_sql="(1, 130, TIMESTAMP '2026-01-01 00:00:00')"),
        setup_commands=(("--no-color", "build", "--target", "prod", "--select", "upstream"),),
        dev_setup_sql=(
            "INSERT INTO main.raw_orders VALUES (2, 131, TIMESTAMP '2026-01-02 00:00:00');\n"
        ),
        command=("--no-color", "build", "--select", "downstream"),
        expected_stdout_fragments=("Reused inputs (1)", "from reuse origin target"),
        unexpected_stdout_fragments=("incremental_append",),
        expected_upstream_rows=((1, 130),),
        expected_downstream_rows=((1, 130),),
        expected_fingerprint_rows=(("model", "downstream"),),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        DeferCloneBuildE2ETestCase(
            description="selected downstream clones missing upstream boundary from prod",
            project_name="defer_clone_build",
            initial_upstream_sql=(
                "MODEL (materialized table);\n\nSELECT 1 AS id, 'prod_version' AS label\n"
            ),
            changed_upstream_sql=(
                "MODEL (materialized table);\n\nSELECT 1 AS id, 'dev_version' AS label\n"
            ),
            downstream_sql=(
                "MODEL (materialized table);\n\n"
                "SELECT id, label || '_downstream' AS label FROM __ref(\"upstream\")\n"
            ),
            prod_build_command=("--no-color", "build", "--target", "prod"),
            dev_build_command=(
                "--no-color",
                "build",
                "--target",
                "dev",
                "--select",
                "downstream",
                "--defer-clone-from",
                "prod",
            ),
            expected_stdout_fragments=(
                "Prephase  defer clone",
                "Existing destination inputs (1)",
                "upstream",
                "[for downstream]",
                "First run (1)",
                "downstream",
                "Completed successfully.",
            ),
            unexpected_stdout_fragments=("cannot build selected scope",),
            expected_prod_upstream_rows=((1, "prod_version"),),
            expected_dev_upstream_rows=((1, "prod_version"),),
            expected_dev_downstream_rows=((1, "prod_version_downstream"),),
            expected_fingerprint_rows=(("model", "downstream"), ("model", "upstream")),
        )
    ],
    ids=["selected downstream clones missing upstream boundary from prod"],
)
def test_given_selected_downstream_when_building_with_defer_clone_then_clones_boundary(
    tmp_path: Path,
    test_case: DeferCloneBuildE2ETestCase,
) -> None:
    assert test_case.expected_stdout_fragments
    assert_defer_clone_build_case(tmp_path=tmp_path, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    DEPENDENCY_BASELINE_TEST_CASES,
    ids=[case.description for case in DEPENDENCY_BASELINE_TEST_CASES],
)
def test_given_dependency_baseline_project_when_building_downstream_then_prepares_upstream(
    tmp_path: Path,
    test_case: DependencyBaselineBuildE2ETestCase,
) -> None:
    assert test_case.expected_stdout_fragments
    assert_dependency_baseline_build_case(tmp_path=tmp_path, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    [
        SelectionAwareStalenessBuildE2ETestCase(
            description="out of selection changed upstream warns without rerunning leaf",
            project_name="selection_aware_staleness_build",
            initial_command=("--no-color", "build"),
            mixed_command=("--no-color", "build", "--select", "b", "c"),
            replan_command=("--no-color", "build", "--select", "c"),
            expected_mixed_stdout_fragments=(
                "selected model 'c' will build on",
                "- a",
                "Completed successfully.",
            ),
            expected_replan_stdout_fragments=(
                "selected model 'c' will build on",
                "- a",
            ),
            unexpected_replan_stdout_fragments=("table      c",),
            expected_c_rows=((1,), (2,)),
        )
    ],
    ids=["out of selection changed upstream warns without rerunning leaf"],
)
def test_given_changed_unselected_upstream_when_building_leaf_then_warns_and_noops(
    tmp_path: Path,
    test_case: SelectionAwareStalenessBuildE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                f'database = "{test_case.project_name}.duckdb"\n'
            ),
            "models/a.sql": "MODEL (materialized table);\n\nselect 1 as id\n",
            "models/b.sql": "MODEL (materialized table);\n\nselect 1 as id\n",
            "models/c.sql": (
                "MODEL (materialized table);\n\n"
                'select * from __ref("a") union all select * from __ref("b")\n'
            ),
        },
    )
    db_path: Path = project_dir / f"{test_case.project_name}.duckdb"
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.initial_command,
        project_dir=project_dir,
    )
    (project_dir / "models" / "a.sql").write_text(
        "MODEL (materialized table);\n\nselect 10 as id\n",
        encoding="utf-8",
    )
    (project_dir / "models" / "b.sql").write_text(
        "MODEL (materialized table);\n\nselect 2 as id\n",
        encoding="utf-8",
    )
    mixed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.mixed_command,
        project_dir=project_dir,
    )
    replan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.replan_command,
        project_dir=project_dir,
    )
    c_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT id FROM main.c ORDER BY id",
    )
    mixed_output: str = mixed_result.stdout + mixed_result.stderr
    replan_output: str = replan_result.stdout + replan_result.stderr

    assert initial_result.returncode == 0
    assert mixed_result.returncode == 0
    assert replan_result.returncode == 0
    expected_fragment: str
    for expected_fragment in test_case.expected_mixed_stdout_fragments:
        assert expected_fragment in mixed_output
    for expected_fragment in test_case.expected_replan_stdout_fragments:
        assert expected_fragment in replan_output
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_replan_stdout_fragments:
        assert unexpected_fragment not in replan_output
    assert tuple(c_rows) == test_case.expected_c_rows


STANDARD_PYTHON_BUILD_HARDENING_TEST_CASES: list[StandardPythonBuildHardeningE2ETestCase] = [
    StandardPythonBuildHardeningE2ETestCase(
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
    StandardPythonBuildHardeningE2ETestCase(
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
    StandardPythonBuildHardeningE2ETestCase(
        description="non json python result payload fails at producer",
        project_name="python_build_non_json_result_project",
        command=("--no-color", "build", "--select", "produce_bad_result"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_build_non_json_result_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_build_non_json_result_project.duckdb"\n'
            ),
            "tasks/bad.py": (
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def produce_bad_result(ctx):\n"
                "    return ctx.result(payload={'bad': {'a', 'b'}})\n"
            ),
        },
        expected_exit_code=1,
        expected_output_fragments=(
            "produce_bad_result",
            "non-JSON-serializable payload",
        ),
    ),
    StandardPythonBuildHardeningE2ETestCase(
        description="non json python result metadata fails at producer",
        project_name="python_build_non_json_metadata_project",
        command=("--no-color", "build", "--select", "produce_bad_metadata"),
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_build_non_json_metadata_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_build_non_json_metadata_project.duckdb"\n'
            ),
            "tasks/bad.py": (
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def produce_bad_metadata(ctx):\n"
                "    return ctx.result(payload={}, metadata={'bad': {'a', 'b'}})\n"
            ),
        },
        expected_exit_code=1,
        expected_output_fragments=(
            "produce_bad_metadata",
            "non-JSON-serializable metadata",
        ),
    ),
    StandardPythonBuildHardeningE2ETestCase(
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
    StandardPythonBuildHardeningE2ETestCase(
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
    StandardPythonBuildHardeningE2ETestCase(
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
    StandardPythonBuildHardeningE2ETestCase(
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
    StandardPythonBuildHardeningE2ETestCase(
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
            description="standard changes-only build prunes unchanged selected model",
            expected_exit_code=0,
            expected_output_fragments=(
                "Plan ready (0 selected)",
                "Skipped current models (1 already up to date)",
            ),
            unexpected_output_fragments=(
                "Execution  sqb build",
                "Completed successfully.",
                "TOTAL=0",
                "1/1",
                "orders up to date",
            ),
        )
    ],
    ids=["standard changes-only build prunes unchanged selected model"],
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
        command=("--no-color", "build"),
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
            description="standard changes-only build executes changed selected model",
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
    ids=["standard changes-only build executes changed selected model"],
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
        command=("--no-color", "build"),
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
            description="direct build persists function hashes in model metadata",
            expected_exit_code=0,
            expected_output_fragments=("fact_orders",),
        )
    ],
    ids=["direct build persists function hashes in model metadata"],
)
def test_given_direct_function_dependency_when_building_then_persists_function_hash_metadata(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_function_metadata_build",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_function_metadata_build"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change full);\n\namount > 100\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT __udf("is_large_order")(150) AS is_large\n'
            ),
        },
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in build_result.stdout, build_result.stdout
    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT metadata_json_b64 FROM main._sqlbuild_fingerprints "
            "WHERE node_name = 'fact_orders' ORDER BY ts DESC LIMIT 1"
        ),
    )
    metadata_json: str = base64.b64decode(str(rows[0][0])).decode("utf-8")
    metadata_payload: dict[str, Any] = json.loads(metadata_json)
    local_function_hashes: dict[str, Any] = metadata_payload["local_function_hashes"]
    assert set(local_function_hashes) == {"is_large_order"}
    assert local_function_hashes["is_large_order"]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="standard changes-only build prunes read-side Python for unchanged SQL",
            expected_exit_code=0,
            expected_output_fragments=(
                "Plan ready (0 selected)",
                "Skipped current models (1 already up to date)",
            ),
            unexpected_output_fragments=(
                "Execution  sqb build",
                "Completed successfully.",
                "TOTAL=0",
                "profile_orders up to date",
                "Python read-side",
            ),
        )
    ],
    ids=["standard changes-only build prunes read-side Python for unchanged SQL"],
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
        command=("--no-color", "build", "--select", "orders profile_orders"),
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
            description="standard normal build appends source freshness after success",
            expected_exit_code=0,
            expected_output_fragments=("Plan ready (1 selected)", "orders", "TOTAL=1"),
            unexpected_output_fragments=(),
        )
    ],
    ids=["standard normal build appends source freshness after success"],
)
def test_given_source_freshness_when_building_normally_then_writes_state_after_success(
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
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in initial_build_result.stdout, initial_build_result.stdout
    assert table_exists(
        db_path=project_dir / "warehouse.duckdb",
        table_name="_sqlbuild_source_freshness",
    )

    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT source_name, data_version FROM main._sqlbuild_source_freshness",
    )
    assert rows == [("raw_orders", "1")]

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    assert "Plan ready (0 selected)" in build_result.stdout
    assert "Skipped current models (1 already up to date)" in build_result.stdout
    assert "Execution  sqb build" not in build_result.stdout
    assert "TOTAL=0" not in build_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="standard changes-only persists plan-time source freshness observation",
            expected_exit_code=0,
            expected_output_fragments=("Plan ready (1 selected)", "orders", "TOTAL=1"),
            unexpected_output_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["standard changes-only persists plan-time source freshness observation"],
)
def test_given_source_freshness_changes_during_build_when_appending_then_persists_plan_time_value(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="standard_source_freshness_plan_time_persistence",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "standard_source_freshness_plan_time_persistence"\n'
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
                "      query: SELECT data_version FROM freshness_control\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="CREATE TABLE freshness_control AS SELECT 0 AS data_version",
    )
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE freshness_control SET data_version = 1",
    )
    (project_dir / "models" / "orders.sql").write_text(
        (
            "MODEL (materialized table, "
            'post_hooks [sql("UPDATE freshness_control SET data_version = 2")]);\n\n'
            'SELECT * FROM __source("raw_orders")\n'
        ),
        encoding="utf-8",
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in build_result.stdout, build_result.stdout
    freshness_control_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT data_version FROM freshness_control",
    )
    freshness_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT source_name, data_version FROM main._sqlbuild_source_freshness "
            "ORDER BY data_version"
        ),
    )
    assert freshness_control_rows == [(2,)]
    assert freshness_rows == [("raw_orders", "0"), ("raw_orders", "1")]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="direct timestamp source freshness respects lag tolerance",
            expected_exit_code=0,
            expected_output_fragments=(
                "Plan ready (0 selected)",
                "Skipped current models (1 already up to date)",
            ),
            unexpected_output_fragments=("Execution  sqb build", "TOTAL=0"),
        )
    ],
    ids=["direct timestamp source freshness respects lag tolerance"],
)
def test_given_timestamp_lag_tolerance_when_building_changes_only_then_skips_within_tolerance(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    source_yml: str = (
        "sources:\n"
        "  - name: raw_orders\n"
        "    expression: SELECT 1 AS order_id\n"
        "    freshness:\n"
        "      strategy: sql\n"
        "      type: timestamp\n"
        "      lag_tolerance: 10m\n"
        "      query: SELECT CAST('{data_version}' AS TIMESTAMP) AS data_version\n"
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_source_freshness_lag_tolerance",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_source_freshness_lag_tolerance"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": source_yml.format(data_version="2026-01-01T12:00:00"),
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
    baseline_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert baseline_result.returncode == 0, baseline_result.stdout + baseline_result.stderr

    (project_dir / "sources" / "raw.yml").write_text(
        source_yml.format(data_version="2026-01-01T12:05:00"), encoding="utf-8"
    )
    within_tolerance_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert within_tolerance_result.returncode == test_case.expected_exit_code, (
        within_tolerance_result.stdout + within_tolerance_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in within_tolerance_result.stdout, within_tolerance_result.stdout

    (project_dir / "sources" / "raw.yml").write_text(
        source_yml.format(data_version="2026-01-01T12:11:00"), encoding="utf-8"
    )
    beyond_tolerance_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert beyond_tolerance_result.returncode == 0, (
        beyond_tolerance_result.stdout + beyond_tolerance_result.stderr
    )
    assert "Plan ready (1 selected)" in beyond_tolerance_result.stdout
    assert "orders" in beyond_tolerance_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="standard source freshness appends independent successful branch only",
            expected_exit_code=1,
            expected_output_fragments=("orders", "payments", "FAIL"),
        )
    ],
    ids=["standard source freshness appends independent successful branch only"],
)
def test_given_independent_source_branch_failure_when_building_then_appends_successful_source_only(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="standard_source_freshness_independent_branch_build",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "standard_source_freshness_independent_branch_build"\n'
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
                "  - name: raw_payments\n"
                "    expression: SELECT 1 AS payment_id\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: integer\n"
                "      query: SELECT 1 AS data_version\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "models/payments.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_payments")\n'
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
    first_changes_only_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert first_changes_only_result.returncode == 0, (
        first_changes_only_result.stdout + first_changes_only_result.stderr
    )
    (project_dir / "sources" / "raw.yml").write_text(
        "sources:\n"
        "  - name: raw_orders\n"
        "    expression: SELECT 1 AS order_id\n"
        "    freshness:\n"
        "      strategy: sql\n"
        "      type: integer\n"
        "      query: SELECT 2 AS data_version\n"
        "  - name: raw_payments\n"
        "    expression: SELECT 1 AS payment_id\n"
        "    freshness:\n"
        "      strategy: sql\n"
        "      type: integer\n"
        "      query: SELECT 2 AS data_version\n",
        encoding="utf-8",
    )
    (project_dir / "models" / "payments.sql").write_text(
        "MODEL (materialized table);\n\nSELECT CAST('bad' AS INTEGER) AS payment_id\n",
        encoding="utf-8",
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in build_result.stdout + build_result.stderr
    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT source_name, COUNT(*) FROM main._sqlbuild_source_freshness "
            "GROUP BY source_name ORDER BY source_name"
        ),
    )
    assert rows == [("raw_orders", 2), ("raw_payments", 1)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="source freshness error blocks affected branch but unrelated branch runs",
            expected_exit_code=1,
            expected_output_fragments=(
                "age errors:",
                "raw_orders",
                "source-blocked models:",
                "stg_orders",
                "fact_orders",
                "dim_customers",
                "SKIP",
                "OK",
                "Blocked by source freshness error",
            ),
        )
    ],
    ids=["source freshness error blocks affected branch but unrelated branch runs"],
)
def test_given_source_freshness_error_when_building_then_blocks_only_affected_branch(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="standard_source_freshness_error_blocks_branch_build",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "standard_source_freshness_error_blocks_branch_build"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": build_freshness_error_branch_source_yml(
                order_id=1,
                customer_id=1,
                order_freshness_query="SELECT CURRENT_TIMESTAMP AS data_version",
                customer_freshness_query="SELECT CURRENT_TIMESTAMP AS data_version",
            ),
            "models/stg_orders.sql": (
                'MODEL (materialized view);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __ref("stg_orders")\n'
            ),
            "models/dim_customers.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_customers")\n'
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
    (project_dir / "sources" / "raw.yml").write_text(
        build_freshness_error_branch_source_yml(
            order_id=2,
            customer_id=2,
            order_freshness_query=(
                "SELECT CAST('2000-01-01 00:00:00' AS TIMESTAMP) AS data_version"
            ),
            customer_freshness_query="SELECT CURRENT_TIMESTAMP AS data_version",
        ),
        encoding="utf-8",
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    output: str = build_result.stdout + build_result.stderr
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output, output
    fact_orders_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id FROM main.fact_orders ORDER BY order_id",
    )
    dim_customers_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT customer_id FROM main.dim_customers ORDER BY customer_id",
    )
    assert fact_orders_rows == [(1,)]
    assert dim_customers_rows == [(2,)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyBuildE2ETestCase(
            description="standard source freshness shared downstream failure blocks all sources",
            expected_exit_code=1,
            expected_output_fragments=("fact_orders", "FAIL"),
        )
    ],
    ids=["standard source freshness shared downstream failure blocks all sources"],
)
def test_given_shared_downstream_failure_when_building_then_blocks_all_source_appends(
    test_case: DirectChangesOnlyBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="standard_source_freshness_shared_failure_build",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "standard_source_freshness_shared_failure_build"\n'
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
                "  - name: raw_payments\n"
                "    expression: SELECT 1 AS payment_id, 1 AS order_id\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: integer\n"
                "      query: SELECT 1 AS data_version\n"
            ),
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT o.order_id, p.payment_id FROM __source("raw_orders") o '
                'JOIN __source("raw_payments") p USING (order_id)\n'
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
    first_changes_only_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert first_changes_only_result.returncode == 0, (
        first_changes_only_result.stdout + first_changes_only_result.stderr
    )
    (project_dir / "sources" / "raw.yml").write_text(
        "sources:\n"
        "  - name: raw_orders\n"
        "    expression: SELECT 1 AS order_id\n"
        "    freshness:\n"
        "      strategy: sql\n"
        "      type: integer\n"
        "      query: SELECT 2 AS data_version\n"
        "  - name: raw_payments\n"
        "    expression: SELECT 1 AS payment_id, 1 AS order_id\n"
        "    freshness:\n"
        "      strategy: sql\n"
        "      type: integer\n"
        "      query: SELECT 2 AS data_version\n",
        encoding="utf-8",
    )
    (project_dir / "models" / "fact_orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT CAST('bad' AS INTEGER) AS order_id\n",
        encoding="utf-8",
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in build_result.stdout + build_result.stderr
    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT source_name, COUNT(*) FROM main._sqlbuild_source_freshness "
            "GROUP BY source_name ORDER BY source_name"
        ),
    )
    assert rows == [("raw_orders", 1), ("raw_payments", 1)]


@pytest.mark.parametrize(
    "test_case",
    STANDARD_PYTHON_BUILD_HARDENING_TEST_CASES,
    ids=[case.description for case in STANDARD_PYTHON_BUILD_HARDENING_TEST_CASES],
)
def test_given_python_lifecycle_edge_case_when_building_then_direct_build_hardens_behavior(
    test_case: StandardPythonBuildHardeningE2ETestCase,
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


STANDARD_SOURCE_ONLY_BUILD_POLICY_TEST_CASES: list[StandardPythonBuildHardeningE2ETestCase] = [
    StandardPythonBuildHardeningE2ETestCase(
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
    StandardPythonBuildHardeningE2ETestCase(
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
    STANDARD_SOURCE_ONLY_BUILD_POLICY_TEST_CASES,
    ids=[case.description for case in STANDARD_SOURCE_ONLY_BUILD_POLICY_TEST_CASES],
)
def test_given_direct_source_only_build_when_loader_has_ingress_then_enforces_source_policy(
    tmp_path: Path,
    test_case: StandardPythonBuildHardeningE2ETestCase,
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
        StandardPythonBuildHardeningE2ETestCase(
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
    test_case: StandardPythonBuildHardeningE2ETestCase,
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
        StandardPythonBuildHardeningE2ETestCase(
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
    test_case: StandardPythonBuildHardeningE2ETestCase,
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
            expected_asset_payload={"order_id": 7},
            expected_asset_materialized="true",
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
                "    payload = ctx.result_of(prepare_orders).payload\n"
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
                "    payload = ctx.result_of(profile_fact_orders).payload\n"
                "    return ctx.result(payload=payload, metadata={'exported': True})\n"
            ),
            "tasks/notify.py": (
                "from pathlib import Path\n"
                "from assets.export import export_fact_orders\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=export_fact_orders)\n"
                "def notify_fact_orders(ctx):\n"
                "    payload = ctx.result_of(export_fact_orders).payload\n"
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
    asset_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT payload_json_b64, materialized FROM _sqlbuild_node_results "
            "WHERE node_type = 'asset' AND node_name = 'publish_prepared_orders'"
        ),
    )
    assert len(asset_rows) == 1
    assert json.loads(base64.b64decode(asset_rows[0][0]).decode("utf-8")) == (
        test_case.expected_asset_payload
    )
    assert asset_rows[0][1] == test_case.expected_asset_materialized


@pytest.mark.parametrize(
    "test_case",
    [
        PythonPersistedResultBuildE2ETestCase(
            description="later task reads persisted history and explicit run id",
            expected_exit_code=0,
            expected_consumed_text="84:42:failed:True:84,42:2",
            expected_success_values=(84, 42),
            expected_failed_status="failed",
        )
    ],
    ids=["later task reads persisted history and explicit run id"],
)
def test_given_prior_python_task_result_when_later_task_reads_result_then_uses_persisted_state(
    test_case: PythonPersistedResultBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_persisted_result_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_persisted_result_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_persisted_result_project.duckdb"\n'
            ),
            "tasks/produce.py": (
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def produce_result(ctx):\n"
                "    return ctx.result(payload={'value': 42}, metadata={'source': 'first'})\n"
            ),
        },
    )

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "produce_result"),
        project_dir=project_dir,
    )
    first_run_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "python_persisted_result_project.duckdb",
        sql="SELECT run_id FROM _sqlbuild_node_results WHERE node_name = 'produce_result'",
    )
    first_run_id: str = str(first_run_rows[0][0])
    (project_dir / "tasks" / "produce.py").write_text(
        (
            "from sqlbuild.tasks import task\n\n"
            "@task\n"
            "def produce_result(ctx):\n"
            "    return ctx.result(payload={'value': 84}, metadata={'source': 'second'})\n"
        ),
        encoding="utf-8",
    )
    updated_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "produce_result"),
        project_dir=project_dir,
    )
    (project_dir / "tasks" / "produce.py").write_text(
        (
            "from sqlbuild.tasks import task\n\n"
            "@task\n"
            "def produce_result(ctx):\n"
            "    raise RuntimeError('producer failed after previous success')\n"
        ),
        encoding="utf-8",
    )
    failed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "produce_result"),
        project_dir=project_dir,
    )
    failed_run_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "python_persisted_result_project.duckdb",
        sql=(
            "SELECT run_id FROM _sqlbuild_node_results "
            "WHERE node_name = 'produce_result' AND status = 'failed'"
        ),
    )
    failed_run_id: str = str(failed_run_rows[0][0])
    (project_dir / "tasks" / "consume.py").write_text(
        (
            "from pathlib import Path\n"
            "from tasks.produce import produce_result\n"
            "from sqlbuild.tasks import task\n\n"
            "@task\n"
            "def consume_result(ctx):\n"
            "    latest = ctx.result_of(produce_result)\n"
            f"    first = ctx.result_of(produce_result, run_id='{first_run_id}')\n"
            f"    failed = ctx.result_of(produce_result, run_id='{failed_run_id}')\n"
            "    history = ctx.results_of(produce_result, limit=2)\n"
            "    values = ','.join(str(item.payload['value']) for item in history)\n"
            "    output = Path(__file__).parents[1].joinpath('consumed.txt')\n"
            "    output.write_text(\n"
            "        f\"{latest.payload['value']}:{first.payload['value']}:\"\n"
            '        f"{failed.status}:{failed.payload is None}:{values}:"\n'
            '        f"{len(history)}"\n'
            "    )\n"
            "    return ctx.result(metadata={'consumed': True})\n"
        ),
        encoding="utf-8",
    )
    second_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "consume_result"),
        project_dir=project_dir,
    )

    assert first_result.returncode == test_case.expected_exit_code, (
        first_result.stdout + first_result.stderr
    )
    assert updated_result.returncode == test_case.expected_exit_code, (
        updated_result.stdout + updated_result.stderr
    )
    assert failed_result.returncode == 1, failed_result.stdout + failed_result.stderr
    assert second_result.returncode == test_case.expected_exit_code, (
        second_result.stdout + second_result.stderr
    )
    assert "produce_result" not in second_result.stdout
    assert (project_dir / "consumed.txt").read_text(encoding="utf-8") == (
        test_case.expected_consumed_text
    )
    result_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "python_persisted_result_project.duckdb",
        sql=(
            "SELECT node_name, status, payload_json_b64, metadata_json_b64 "
            "FROM _sqlbuild_node_results WHERE node_name = 'produce_result' "
            "ORDER BY ts DESC"
        ),
    )
    assert len(result_rows) == 3
    assert result_rows[0][1] == test_case.expected_failed_status
    successful_values: tuple[int, ...] = tuple(
        int(json.loads(base64.b64decode(row[2]).decode("utf-8"))["value"])
        for row in result_rows
        if row[1] == "success"
    )
    assert successful_values == test_case.expected_success_values
    successful_metadata: tuple[object, ...] = tuple(
        json.loads(base64.b64decode(row[3]).decode("utf-8"))["source"]
        for row in result_rows
        if row[1] == "success"
    )
    assert successful_metadata == ("second", "first")


@pytest.mark.parametrize(
    "test_case",
    [
        PythonLoaderPersistedResultBuildE2ETestCase(
            description="later task reads prior persisted loader result",
            expected_exit_code=0,
            expected_loader_text="raw_events:raw_events:1",
        )
    ],
    ids=["later task reads prior persisted loader result"],
)
def test_given_prior_loader_result_when_later_task_reads_result_then_uses_loader_summary(
    test_case: PythonLoaderPersistedResultBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_persisted_loader_result_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_persisted_loader_result_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_persisted_loader_result_project.duckdb"\n'
            ),
            "loaders/events.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
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
            "models/fact_events.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_events")\n'
            ),
            "tasks/consume.py": (
                "from pathlib import Path\n"
                "from loaders.events import raw_events\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def consume_loader_result(ctx):\n"
                "    result = ctx.result_of(raw_events)\n"
                "    output = Path(__file__).parents[1].joinpath('loader_result.txt')\n"
                "    output.write_text(\n"
                "        f\"{result.metadata['loader_name']}:{result.metadata['source_name']}:\"\n"
                "        f\"{result.metadata['rows_loaded']}\"\n"
                "    )\n"
                "    return ctx.result()\n"
            ),
        },
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "fact_events"),
        project_dir=project_dir,
    )
    consume_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "consume_loader_result"),
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    assert consume_result.returncode == test_case.expected_exit_code, (
        consume_result.stdout + consume_result.stderr
    )
    assert "raw_events" not in consume_result.stdout
    assert (project_dir / "loader_result.txt").read_text(encoding="utf-8") == (
        test_case.expected_loader_text
    )


LOADER_STATUS_RESULT_TEST_CASES: tuple[PythonLoaderStatusResultBuildE2ETestCase, ...] = (
    PythonLoaderStatusResultBuildE2ETestCase(
        description="failed loader persists failed result row",
        project_name="python_failed_loader_result_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_failed_loader_result_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_failed_loader_result_project.duckdb"\n'
            ),
            "loaders/events.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_events(ctx):\n"
                "    raise RuntimeError('loader failed')\n"
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
            "models/fact_events.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_events")\n'
            ),
        },
        command=("--no-color", "build", "--select", "fact_events"),
        expected_exit_code=1,
        expected_rows=(("raw_events", "failed", "loader failed"),),
    ),
    PythonLoaderStatusResultBuildE2ETestCase(
        description="skipped loader persists skipped result row",
        project_name="python_skipped_loader_result_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_skipped_loader_result_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_skipped_loader_result_project.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from sqlbuild.compiler.python_nodes.types import SkipMode\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_events(ctx):\n"
                "    return ctx.skip('no input', mode=SkipMode.HARD)\n"
            ),
            "loaders/events.py": (
                "from tasks.prepare import prepare_events\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader(depends_on=(prepare_events,))\n"
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
            "models/fact_events.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_events")\n'
            ),
        },
        command=("--no-color", "build", "--select", "+fact_events"),
        expected_exit_code=0,
        expected_rows=(("raw_events", "skipped", "Upstream node hard-skipped: prepare_events"),),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    LOADER_STATUS_RESULT_TEST_CASES,
    ids=[case.description for case in LOADER_STATUS_RESULT_TEST_CASES],
)
def test_given_loader_status_result_when_building_then_persists_loader_status_row(
    test_case: PythonLoaderStatusResultBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert (
        tuple(
            query_duckdb(
                db_path=project_dir / f"{test_case.project_name}.duckdb",
                sql=(
                    "SELECT node_name, status, error_message "
                    "FROM _sqlbuild_node_results WHERE node_type = 'loader' ORDER BY node_name"
                ),
            )
        )
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonTargetIsolationBuildE2ETestCase(
            description="same node name reads only active target result",
            expected_exit_code=0,
            expected_consumed_text="dev",
            expected_target_rows=(
                ("dev", "dev"),
                ("prod", "prod"),
            ),
        )
    ],
    ids=["same node name reads only active target result"],
)
def test_given_same_node_results_in_multiple_targets_when_reading_then_uses_active_target(
    test_case: PythonTargetIsolationBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_result_target_isolation_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_result_target_isolation_project"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                'database = "python_result_target_isolation_project.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.prod]\n"
                'schema = "prod"\n'
            ),
            "tasks/produce.py": (
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def produce_result(ctx):\n"
                "    return ctx.result(payload={'target': ctx.target})\n"
            ),
            "tasks/consume.py": (
                "from pathlib import Path\n"
                "from tasks.produce import produce_result\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def consume_result(ctx):\n"
                "    result = ctx.result_of(produce_result)\n"
                "    output = Path(__file__).parents[1].joinpath('target_result.txt')\n"
                "    output.write_text(str(result.payload['target']))\n"
                "    return ctx.result()\n"
            ),
        },
    )

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "produce_result"),
        project_dir=project_dir,
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "produce_result"),
        project_dir=project_dir,
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    consume_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "consume_result"),
        project_dir=project_dir,
    )

    assert dev_result.returncode == test_case.expected_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert prod_result.returncode == test_case.expected_exit_code, (
        prod_result.stdout + prod_result.stderr
    )
    assert consume_result.returncode == test_case.expected_exit_code, (
        consume_result.stdout + consume_result.stderr
    )
    assert (project_dir / "target_result.txt").read_text(encoding="utf-8") == (
        test_case.expected_consumed_text
    )
    target_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "python_result_target_isolation_project.duckdb",
        sql=(
            "SELECT target_schema, payload_json_b64 FROM ("
            "SELECT target_schema, payload_json_b64 FROM dev._sqlbuild_node_results "
            "WHERE node_name = 'produce_result' "
            "UNION ALL "
            "SELECT target_schema, payload_json_b64 FROM prod._sqlbuild_node_results "
            "WHERE node_name = 'produce_result'"
            ") ORDER BY target_schema"
        ),
    )
    decoded_rows: tuple[tuple[object, ...], ...] = tuple(
        (row[0], json.loads(base64.b64decode(row[1]).decode("utf-8"))["target"])
        for row in target_rows
    )
    assert decoded_rows == test_case.expected_target_rows


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
