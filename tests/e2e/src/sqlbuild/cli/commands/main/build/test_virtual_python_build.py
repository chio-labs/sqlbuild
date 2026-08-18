from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualNodeResultFailureStateE2ETestCase,
    VirtualNodeResultStateE2ETestCase,
    VirtualPythonBuildE2ETestCase,
    VirtualPythonHooksBuildE2ETestCase,
    VirtualPythonIdentityBuildE2ETestCase,
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
        VirtualPythonHooksBuildE2ETestCase(
            description="virtual build executes discovered Python lifecycle hook",
            expected_exit_code=0,
            expected_model_rows=((7,),),
            expected_hook_log_rows=(("fact_orders", "post_hooks"),),
            expected_identity_rows=(("hook", "log_virtual_hook"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_build_with_python_hooks_when_building_then_hooks_execute(
    test_case: VirtualPythonHooksBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_python_hooks_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "hooks/lifecycle.py": dedent(
                """
                from sqlbuild.hooks import hook


                @hook
                def log_virtual_hook(ctx):
                    ctx.execute_sql(
                        "CREATE TABLE main.virtual_hook_log AS "
                        f"SELECT '{ctx.model_name}' AS model_name, '{ctx.phase}' AS phase"
                    )
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": dedent(
                """
                MODEL (
                  materialized table,
                  post_hooks [python("log_virtual_hook")]
                );

                SELECT 7 AS id
                """
            ).strip()
            + "\n",
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    db_path: Path = project_dir / "warehouse.duckdb"

    assert build_result.returncode == test_case.expected_exit_code, build_result.stderr
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_model_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT model_name, phase FROM main.virtual_hook_log",
    ) == list(test_case.expected_hook_log_rows)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_type, node_name "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE node_type IN ('task', 'loader', 'asset', 'check', 'hook') "
            "ORDER BY node_type, node_name"
        ),
    ) == list(test_case.expected_identity_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonBuildE2ETestCase(
            description="runs loader-side and read-side Python nodes",
            project_name="virtual_python_nodes_build",
            plan_command=("--no-color", "plan", "--select", "+fact_orders"),
            build_command=("--no-color", "build", "--select", "+fact_orders"),
            expected_build_exit_code=0,
            expected_plan_fragments=(
                "Python ingress (1)",
                "prepare_orders",
                "Python read-side (2)",
                "profile_fact_orders",
                "profile_raw_orders",
            ),
            expected_prepared_text="7",
            expected_profile_text="1",
            expected_source_profile_text="1",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_python_nodes_when_building_then_runs_loader_and_read_side_python(
    test_case: VirtualPythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_python_nodes_build"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'defer_sources_to = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from pathlib import Path\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    Path(__file__).parents[1].joinpath('prepared.txt').write_text('7')\n"
                "    return ctx.result(payload={'order_id': 7})\n"
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_orders\n\n"
                "@loader(depends_on=(prepare_orders,))\n"
                "def raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
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
                "from pathlib import Path\n"
                "from sqlbuild.refs import model, source\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    relation = ctx.relation(model('fact_orders'))\n"
                "    rows = ctx.query(f'SELECT COUNT(*) FROM {relation}').fetchall()[0][0]\n"
                "    Path(__file__).parents[1].joinpath('profile.txt').write_text(str(rows))\n"
                "    return ctx.result(payload={'rows': rows})\n"
                "\n"
                "@task(depends_on=source('raw_orders'))\n"
                "def profile_raw_orders(ctx):\n"
                "    relation = ctx.relation(source('raw_orders'))\n"
                "    rows = ctx.query(f'SELECT COUNT(*) FROM {relation}').fetchall()[0][0]\n"
                "    output = Path(__file__).parents[1].joinpath('source_profile.txt')\n"
                "    output.write_text(str(rows))\n"
                "    return ctx.result(payload={'rows': rows})\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.plan_command,
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    for fragment in test_case.expected_plan_fragments:
        assert fragment in plan_result.stdout

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_build_exit_code, (
        build_result.stdout + build_result.stderr
    )
    assert (project_dir / "prepared.txt").read_text(encoding="utf-8") == (
        test_case.expected_prepared_text
    )
    assert (project_dir / "profile.txt").read_text(encoding="utf-8") == (
        test_case.expected_profile_text
    )
    assert (project_dir / "source_profile.txt").read_text(encoding="utf-8") == (
        test_case.expected_source_profile_text
    )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualNodeResultStateE2ETestCase(
            description="persists loader task asset and check node results in virtual state",
            expected_state_rows=(
                ("dev", "asset", "publish_result", "success"),
                ("dev", "check", "check_produce_result", "success"),
                ("dev", "loader", "raw_orders", "success"),
                ("dev", "task", "produce_result", "success"),
                ("dev", "task", "summarize_loader", "success"),
            ),
            expected_asset_payload={"value": 42},
            expected_loader_text="raw_orders:raw_orders:1",
            expected_history_text="42:1",
            expected_warehouse_result_table_count=0,
            expected_build_fragments=("check_produce_result", "PASS"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_python_result_when_building_then_persists_node_results_in_state(
    test_case: VirtualNodeResultStateE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_node_results_state",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_node_results_state"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                'defer_sources_to = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "loaders/orders.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    return [{'value': 42}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: value\n"
                "        type: INTEGER\n"
            ),
            "tasks/results.py": (
                "from pathlib import Path\n"
                "from loaders.orders import raw_orders\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('orders'))\n"
                "def produce_result(ctx):\n"
                "    return ctx.result(payload={'value': 42}, metadata={'source': 'vde'})\n"
                "\n"
                "@task(depends_on=model('orders'))\n"
                "def summarize_loader(ctx):\n"
                "    result = ctx.result_of(node_function=raw_orders)\n"
                "    history = ctx.results_of(node_function=raw_orders, limit=1)\n"
                "    output = Path(__file__).parents[1].joinpath('loader_result.txt')\n"
                "    output.write_text(\n"
                "        f\"{result.metadata['loader_name']}:{result.metadata['source_name']}:\"\n"
                "        f\"{result.metadata['rows_loaded']}\"\n"
                "    )\n"
                "    history_output = Path(__file__).parents[1].joinpath('history_result.txt')\n"
                "    history_output.write_text(\n"
                "        f\"{ctx.result_of(node_function=produce_result).payload['value']}:{len(history)}\"\n"
                "    )\n"
                "    return ctx.result(metadata={'summarized': True})\n"
            ),
            "assets/results.py": (
                "from sqlbuild.assets import asset\n"
                "from tasks.results import produce_result\n\n"
                "@asset(depends_on=produce_result)\n"
                "def publish_result(ctx):\n"
                "    payload = ctx.result_of(node_function=produce_result).payload\n"
                "    return ctx.result(payload=payload, materialized=True)\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT value FROM __source("raw_orders")\n'
            ),
            "checks/results.py": (
                "from sqlbuild.checks import check\n"
                "from assets.results import publish_result\n"
                "from tasks.results import produce_result, summarize_loader\n\n"
                "@check(depends_on=(publish_result, summarize_loader))\n"
                "def check_produce_result(ctx):\n"
                "    return (\n"
                "        ctx.result_of(node_function=produce_result).payload['value'] == 42\n"
                "        and ctx.result_of(node_function=publish_result).payload['value'] == 42\n"
                "    )\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "orders"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    for fragment in test_case.expected_build_fragments:
        assert fragment in build_result.stdout
    state_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT virtual_environment_name, node_type, node_name, status "
            "FROM sqlbuild_state.node_results "
            "WHERE node_name IN ("
            "'raw_orders', 'produce_result', 'summarize_loader', "
            "'publish_result', 'check_produce_result') "
            "ORDER BY node_type, node_name"
        ),
    )
    assert state_rows == list(test_case.expected_state_rows)
    asset_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT payload_json_b64, materialized FROM sqlbuild_state.node_results "
            "WHERE node_type = 'asset' AND node_name = 'publish_result'"
        ),
    )
    assert len(asset_rows) == 1
    assert json.loads(base64.b64decode(str(asset_rows[0][0])).decode("utf-8")) == (
        test_case.expected_asset_payload
    )
    assert asset_rows[0][1] == "true"
    assert (project_dir / "loader_result.txt").read_text(encoding="utf-8") == (
        test_case.expected_loader_text
    )
    assert (project_dir / "history_result.txt").read_text(encoding="utf-8") == (
        test_case.expected_history_text
    )
    warehouse_result_table_count: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = '_sqlbuild_node_results'"
        ),
    )
    assert warehouse_result_table_count == [(test_case.expected_warehouse_result_table_count,)]


@pytest.mark.parametrize(
    "test_case",
    (
        VirtualNodeResultFailureStateE2ETestCase(
            description="failed virtual task persists failed state row",
            project_name="virtual_failed_task_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_failed_task_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def produce_result(ctx):\n"
                    "    raise RuntimeError('producer failed')\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=1,
            expected_state_rows=(("task", "produce_result", "failed", "producer failed"),),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="failed virtual check persists failed state row",
            project_name="virtual_failed_check_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_failed_check_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def produce_result(ctx):\n"
                    "    return ctx.result(payload={'value': 1})\n"
                ),
                "checks/results.py": (
                    "from sqlbuild.checks import check\n"
                    "from tasks.results import produce_result\n\n"
                    "@check(depends_on=produce_result)\n"
                    "def check_produce_result(ctx):\n"
                    "    return False\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=1,
            expected_state_rows=(
                ("check", "check_produce_result", "failed", ""),
                ("task", "produce_result", "success", ""),
            ),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="skipped virtual task persists skipped state row",
            project_name="virtual_skipped_task_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_skipped_task_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.compiler.python_nodes.types import SkipMode\n"
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def prepare_orders(ctx):\n"
                    "    return ctx.skip(reason='not needed', mode=SkipMode.SOFT)\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=0,
            expected_state_rows=(("task", "prepare_orders", "skipped", "not needed"),),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="skipped virtual loader persists skipped state row",
            project_name="virtual_skipped_loader_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_skipped_loader_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"
                defer_sources_to = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "tasks/prepare.py": (
                    "from sqlbuild.compiler.python_nodes.types import SkipMode\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task\n"
                    "def prepare_events(ctx):\n"
                    "    return ctx.skip(reason='no input', mode=SkipMode.HARD)\n"
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
                "models/events.sql": (
                    'MODEL (materialized table);\n\nSELECT * FROM __source("raw_events")\n'
                ),
            },
            command=("--no-color", "build", "--select", "+events"),
            expected_exit_code=0,
            expected_state_rows=(
                ("loader", "raw_events", "skipped", "Upstream node hard-skipped: prepare_events"),
                ("task", "prepare_events", "skipped", "no input"),
            ),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="non JSON virtual payload persists failed state row",
            project_name="virtual_non_json_payload_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_non_json_payload_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def produce_result(ctx):\n"
                    "    return ctx.result(payload={'bad': {1, 2}})\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=1,
            expected_state_rows=(("task", "produce_result", "failed", "non-JSON-serializable"),),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="non JSON virtual metadata persists failed state row",
            project_name="virtual_non_json_metadata_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_non_json_metadata_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def produce_result(ctx):\n"
                    "    return ctx.result(payload={'ok': True}, metadata={'bad': {1, 2}})\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=1,
            expected_state_rows=(("task", "produce_result", "failed", "non-JSON-serializable"),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_virtual_node_result_failure_when_building_then_persists_failed_state_row(
    test_case: VirtualNodeResultFailureStateE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files=test_case.repo_files,
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    state_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_type, node_name, status, error_message "
            "FROM sqlbuild_state.node_results ORDER BY node_type, node_name"
        ),
    )
    assert len(state_rows) == len(test_case.expected_state_rows)
    actual_row: tuple[object, ...]
    expected_row: tuple[object, ...]
    for actual_row, expected_row in zip(state_rows, test_case.expected_state_rows, strict=True):
        assert actual_row[:3] == expected_row[:3]
        assert str(expected_row[3]) in str(actual_row[3] or "")


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonIdentityBuildE2ETestCase(
            description="stores Python identities in virtual state for later planning",
            expected_state_identity_rows=(
                ("loader", "raw_orders"),
                ("task", "prepare_orders"),
                ("task", "profile_fact_orders"),
            ),
            expected_warehouse_fingerprint_table_count=0,
            expected_changed_plan_fragments=(
                "Plan ready  0 selected",
                "Python ingress (1)",
                "prepare_orders",
                "task (changed)",
                "python diff:",
                "source diff:",
            ),
            unexpected_changed_plan_fragments=(
                "First run (",
                "Query changed (",
                "fact_orders          table",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_python_identities_when_replanning_then_reads_virtual_state(
    test_case: VirtualPythonIdentityBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_python_identity_state",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_python_identity_state"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'defer_sources_to = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from pathlib import Path\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    Path(__file__).parents[1].joinpath('prepared.txt').write_text('7')\n"
                "    return ctx.result(payload={'order_id': 7})\n"
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_orders\n\n"
                "@loader(depends_on=(prepare_orders,))\n"
                "def raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
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
                "from pathlib import Path\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    relation = ctx.relation(model('fact_orders'))\n"
                "    rows = ctx.query(f'SELECT COUNT(*) FROM {relation}').fetchall()[0][0]\n"
                "    Path(__file__).parents[1].joinpath('profile.txt').write_text(str(rows))\n"
                "    return ctx.result(payload={'rows': rows})\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_type, node_name "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE node_type IN ('task', 'loader', 'asset', 'check', 'hook') "
            "ORDER BY node_type, node_name"
        ),
    ) == list(test_case.expected_state_identity_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = '_sqlbuild_fingerprints'"
        ),
    ) == [(test_case.expected_warehouse_fingerprint_table_count,)]

    (project_dir / "tasks" / "prepare.py").write_text(
        "from pathlib import Path\n"
        "from sqlbuild.tasks import task\n\n"
        "@task\n"
        "def prepare_orders(ctx):\n"
        "    Path(__file__).parents[1].joinpath('prepared.txt').write_text('8')\n"
        "    return ctx.result(payload={'order_id': 8})\n",
        encoding="utf-8",
    )
    changed_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "+fact_orders", "--changes-only"),
        project_dir=project_dir,
    )
    assert changed_plan_result.returncode == 0, (
        changed_plan_result.stdout + changed_plan_result.stderr
    )
    for fragment in test_case.expected_changed_plan_fragments:
        assert fragment in changed_plan_result.stdout
    for fragment in test_case.unexpected_changed_plan_fragments:
        assert fragment not in changed_plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonBuildE2ETestCase(
            description="prints read-side Python failure rows",
            project_name="virtual_python_read_side_failure",
            plan_command=(),
            build_command=("--no-color", "build", "--select", "+fact_orders"),
            expected_build_exit_code=1,
            expected_build_fragments=(
                "python    task      profile_fact_orders",
                "FAIL",
                "profile failed intentionally",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_read_side_python_failure_when_building_then_prints_python_failure_row(
    test_case: VirtualPythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_python_read_side_failure"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/fact_orders.sql": "MODEL (materialized table);\n\nSELECT 7 AS order_id\n",
            "tasks/profile.py": (
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    raise RuntimeError('profile failed intentionally')\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_build_exit_code
    for fragment in test_case.expected_build_fragments:
        assert fragment in build_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonBuildE2ETestCase(
            description="prints read-side Python skip rows",
            project_name="virtual_python_read_side_skip",
            plan_command=(),
            build_command=("--no-color", "build", "--select", "+fact_orders"),
            expected_build_exit_code=0,
            expected_build_fragments=(
                "python    task      skip_fact_orders",
                "SKIP",
                "profile not needed",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_read_side_python_skip_when_building_then_prints_python_skip_row(
    test_case: VirtualPythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_python_read_side_skip"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/fact_orders.sql": "MODEL (materialized table);\n\nSELECT 7 AS order_id\n",
            "tasks/profile.py": (
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def skip_fact_orders(ctx):\n"
                "    return ctx.skip(reason='profile not needed')\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_build_exit_code
    for fragment in test_case.expected_build_fragments:
        assert fragment in build_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonBuildE2ETestCase(
            description="no-python only runs loader-side Python nodes",
            project_name="virtual_no_python_nodes_build",
            plan_command=("--no-color", "plan", "--select", "+fact_orders", "--no-python"),
            build_command=("--no-color", "build", "--select", "+fact_orders", "--no-python"),
            expected_build_exit_code=0,
            expected_plan_fragments=("Python ingress (1)", "prepare_orders"),
            expected_absent_plan_fragments=("Python read-side", "profile_fact_orders"),
            expected_prepared_text="7",
            expected_profile_exists=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_python_nodes_when_no_python_then_only_loader_side_python_runs(
    test_case: VirtualPythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_no_python_nodes_build"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'defer_sources_to = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from pathlib import Path\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    Path(__file__).parents[1].joinpath('prepared.txt').write_text('7')\n"
                "    return ctx.result(payload={'order_id': 7})\n"
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_orders\n\n"
                "@loader(depends_on=(prepare_orders,))\n"
                "def raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
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
                "from pathlib import Path\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    Path(__file__).parents[1].joinpath('profile.txt').write_text('ran')\n"
                "    return ctx.result()\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.plan_command,
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    for fragment in test_case.expected_plan_fragments:
        assert fragment in plan_result.stdout
    for fragment in test_case.expected_absent_plan_fragments:
        assert fragment not in plan_result.stdout

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_build_exit_code, (
        build_result.stdout + build_result.stderr
    )
    assert (project_dir / "prepared.txt").read_text(encoding="utf-8") == (
        test_case.expected_prepared_text
    )
    assert (project_dir / "profile.txt").exists() is test_case.expected_profile_exists
