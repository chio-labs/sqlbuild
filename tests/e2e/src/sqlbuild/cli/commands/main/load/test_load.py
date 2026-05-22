from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.load._test_types import (
    ChainedLoaderFailureE2ETestCase,
    ChainedLoaderPruningE2ETestCase,
    ChainedLoaderSelectionE2ETestCase,
    IntermediateLoaderStrategyE2ETestCase,
    LoaderWaffleShopE2ETestCase,
    SourceLoaderErrorE2ETestCase,
    SourceLoaderSchemaEvolutionE2ETestCase,
    SourceLoaderStrategiesE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.load.helpers import (
    build_loader_waffle_shop_project_files,
    build_schema_behavior_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    prepare_source_loader_strategies,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderStrategiesE2ETestCase(
            description="source loader strategies apply expected rows across two loads",
            command=("--no-color", "load", "--concurrency", "4"),
            expected_countries=((1, "US", "United States"), (2, "CA", "Canada")),
            expected_webhook_event_counts=((101, "signup", 2), (102, "checkout", 2)),
            expected_order_events=((201, 1000), (202, 2500), (203, 3000)),
            expected_customers=((1, "pro"), (2, "trial"), (3, "enterprise")),
            expected_loader_status=((1, "loaded", "self_managed"),),
            expected_stdout_fragments=(
                "raw_countries",
                "raw_webhook_events",
                "raw_order_events",
                "raw_customers",
                "raw_loader_status",
            ),
        )
    ],
    ids=["source loader strategies apply expected rows across two loads"],
)
def test_given_source_loader_strategy_project_when_loading_twice_then_all_write_modes_apply(
    tmp_path: Path,
    test_case: SourceLoaderStrategiesE2ETestCase,
) -> None:
    project_dir: Path = prepare_source_loader_strategies(tmp_path=tmp_path)
    db_path: Path = project_dir / "source_loader_strategies.duckdb"

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    second_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert first_result.returncode == test_case.expected_return_code, (
        first_result.stdout + first_result.stderr
    )
    assert second_result.returncode == test_case.expected_return_code, (
        second_result.stdout + second_result.stderr
    )
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in second_result.stdout

    countries: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT country_id, country_code, country_name FROM raw_countries ORDER BY country_id"
        ),
    )
    webhook_event_counts: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT event_id, event_name, COUNT(*) FROM raw_webhook_events "
            "GROUP BY event_id, event_name ORDER BY event_id"
        ),
    )
    order_events: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, amount_cents FROM raw_order_events ORDER BY event_id",
    )
    customers: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT customer_id, plan_name FROM raw_customers ORDER BY customer_id",
    )
    loader_status: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=("SELECT status_id, status_name, loaded_by FROM raw_loader_status ORDER BY status_id"),
    )

    assert tuple(countries) == test_case.expected_countries
    assert tuple(webhook_event_counts) == test_case.expected_webhook_event_counts
    assert tuple(order_events) == test_case.expected_order_events
    assert tuple(customers) == test_case.expected_customers
    assert tuple(loader_status) == test_case.expected_loader_status


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderSchemaEvolutionE2ETestCase(
            description="non-contract source adds late columns to existing append target",
            command=("--no-color", "load"),
            expected_rows=((1, None), (2, "late-note")),
        )
    ],
    ids=["non-contract source adds late columns to existing append target"],
)
def test_given_non_contract_loader_when_late_column_appears_then_existing_target_evolves(
    tmp_path: Path,
    test_case: SourceLoaderSchemaEvolutionE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    loader: raw_events\n"
                "    write_strategy: append\n"
                "    cursor_column: load_seq\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: load_seq\n"
                "        type: INTEGER\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_events(ctx):\n"
                "    if ctx.current_cursor_value is None:\n"
                "        return [{'event_id': 1, 'load_seq': 1}]\n"
                "    return [{'event_id': 2, 'load_seq': 2, 'note': 'late-note'}]\n"
            ),
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    second_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert first_result.returncode == test_case.expected_return_code, (
        first_result.stdout + first_result.stderr
    )
    assert second_result.returncode == test_case.expected_return_code, (
        second_result.stdout + second_result.stderr
    )
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, note FROM raw_events ORDER BY event_id",
    )
    assert tuple(rows) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        LoaderWaffleShopE2ETestCase(
            description="loader focused waffle shop grows across repeated builds",
            command=("--no-color", "build", "--select", "+customer_revenue"),
            run_count=3,
            expected_order_count=6,
            expected_customer_revenue_rows=(
                (1, "pro", 650, 1),
                (2, "plus", 6750, 3),
                (3, "enterprise", 3250, 2),
            ),
            expected_intermediate_counts=(
                ("__loader__fetch_order_events", 6),
                ("__loader__fetch_prices", 2),
                ("__loader__fetch_customers", 3),
            ),
        )
    ],
    ids=["loader focused waffle shop grows across repeated builds"],
)
def test_given_loader_waffle_shop_project_when_building_repeatedly_then_dag_grows_models(
    tmp_path: Path,
    test_case: LoaderWaffleShopE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="loader_waffle_shop",
        repo_files=build_loader_waffle_shop_project_files(),
    )
    db_path: Path = project_dir / "loader_waffle_shop.duckdb"

    for _ in range(test_case.run_count):
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )
        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        assert "loader    fetch_order_events" in result.stdout
        assert "loader    fetch_prices" in result.stdout
        assert "loader    fetch_customers" in result.stdout
        assert "source    raw_orders" in result.stdout
        assert "source    raw_customers" in result.stdout

    order_count_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT COUNT(*) FROM fact_waffle_orders",
    )
    customer_revenue_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT customer_id, plan_name, revenue_cents, order_count "
            "FROM customer_revenue ORDER BY customer_id"
        ),
    )
    assert int(order_count_rows[0][0]) == test_case.expected_order_count
    assert tuple(customer_revenue_rows) == test_case.expected_customer_revenue_rows
    for relation_name, expected_count in test_case.expected_intermediate_counts:
        count_rows: list[tuple[object, ...]] = query_duckdb(
            db_path=db_path,
            sql=f"SELECT COUNT(*) FROM {relation_name}",
        )
        assert int(count_rows[0][0]) == expected_count


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderErrorE2ETestCase(
            description="plan separates intermediate loaders and terminal sources",
            repo_files=build_loader_waffle_shop_project_files(),
            command=("--no-color", "plan", "--select", "+customer_revenue"),
            expected_error_fragment="",
            expected_return_code=0,
        )
    ],
    ids=["plan separates intermediate loaders and terminal sources"],
)
def test_given_loader_waffle_shop_project_when_planning_then_shows_loader_dag_sections(
    tmp_path: Path,
    test_case: SourceLoaderErrorE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="loader_waffle_shop",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert "Loaders to load (3)" in result.stdout
    assert "fetch_order_events" in result.stdout
    assert "fetch_prices" in result.stdout
    assert "fetch_customers" in result.stdout
    assert "Sources to load (2)" in result.stdout
    assert "raw_orders" in result.stdout
    assert "raw_customers" in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderSchemaEvolutionE2ETestCase(
            description="shared intermediate runs once for multiple terminal sources",
            command=(
                "--no-color",
                "load",
                "--select",
                "raw_orders",
                "--select",
                "raw_order_metrics",
            ),
            expected_rows=((1,), (2,)),
        )
    ],
    ids=["shared intermediate runs once for multiple terminal sources"],
)
def test_given_two_terminal_sources_when_sharing_intermediate_then_intermediate_runs_once(
    tmp_path: Path,
    test_case: SourceLoaderSchemaEvolutionE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_orders\n"
                "    loader: raw_orders\n"
                "    write_strategy: table\n"
                "  - name: raw_order_metrics\n"
                "    loader: raw_order_metrics\n"
                "    write_strategy: table\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='append', cursor_column='load_seq', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_orders(ctx):\n"
                "    if ctx.current_cursor_value is None:\n"
                "        next_seq = 1\n"
                "    else:\n"
                "        next_seq = ctx.current_cursor_value + 1\n"
                "    return [{'event_id': next_seq, 'load_seq': next_seq}]\n\n"
                "@loader(depends_on=[fetch_orders])\n"
                "def raw_orders(ctx):\n"
                "    orders = ctx.loader(fetch_orders)\n"
                "    cursor = ctx.query(\n"
                "        f'SELECT event_id FROM {orders.target} ORDER BY event_id'\n"
                "    )\n"
                "    return [{'event_id': row[0]} for row in cursor.fetchall()]\n\n"
                "@loader(depends_on=[fetch_orders])\n"
                "def raw_order_metrics(ctx):\n"
                "    orders = ctx.loader(fetch_orders)\n"
                "    cursor = ctx.query(\n"
                "        f'SELECT event_id FROM {orders.target} ORDER BY event_id'\n"
                "    )\n"
                "    return [{'event_id': row[0]} for row in cursor.fetchall()]\n"
            ),
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    for _ in range(2):
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )
        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr

    intermediate_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id FROM __loader__fetch_orders ORDER BY event_id",
    )
    raw_orders_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id FROM raw_orders ORDER BY event_id",
    )
    raw_metrics_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id FROM raw_order_metrics ORDER BY event_id",
    )
    assert tuple(intermediate_rows) == test_case.expected_rows
    assert tuple(raw_orders_rows) == test_case.expected_rows
    assert tuple(raw_metrics_rows) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderSchemaEvolutionE2ETestCase(
            description="chained loader writes intermediate and terminal source tables",
            command=("--no-color", "load", "--select", "raw_events"),
            expected_rows=((1, "loaded", 1), (2, "loaded", 1)),
        )
    ],
    ids=["chained loader writes intermediate and terminal source tables"],
)
def test_given_chained_loader_project_when_loading_source_then_runs_dependencies_first(
    tmp_path: Path,
    test_case: SourceLoaderSchemaEvolutionE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    loader: raw_events\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                "        type: VARCHAR\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', cursor_column='load_seq', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    source_cursor = ctx.source('raw_events').max('event_id')\n"
                "    return [\n"
                "        {'event_id': 1, 'load_seq': 1},\n"
                "        {'event_id': 2, 'load_seq': 1},\n"
                "    ] if source_cursor is None else []\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                "SELECT event_id, 'loaded' AS status, {events.current_cursor_value} AS max_seq "
                'FROM {events.target}")\n'
            ),
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert "loader    fetch_events" in result.stdout
    assert "source    raw_events" in result.stdout
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, status, max_seq FROM raw_events ORDER BY event_id",
    )
    intermediate_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, load_seq FROM __loader__fetch_events ORDER BY event_id",
    )
    assert tuple(rows) == test_case.expected_rows
    assert tuple(intermediate_rows) == ((1, 1), (2, 1))


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderSchemaEvolutionE2ETestCase(
            description="build auto-loads intermediate loader dependencies",
            command=("--no-color", "build", "--select", "+fact_events"),
            expected_rows=((1, "loaded"), (2, "loaded")),
        )
    ],
    ids=["build auto-loads intermediate loader dependencies"],
)
def test_given_chained_loader_project_when_building_source_model_then_runs_loader_dag(
    tmp_path: Path,
    test_case: SourceLoaderSchemaEvolutionE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    loader: raw_events\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                "        type: VARCHAR\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    return [{'event_id': 1}, {'event_id': 2}]\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                "SELECT event_id, 'loaded' AS status FROM {events.target}\")\n"
            ),
        )
        | {
            "models/fact_events.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT event_id, status FROM __source("raw_events")\n'
            )
        },
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert "loader    fetch_events" in result.stdout
    assert "source    raw_events" in result.stdout
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, status FROM fact_events ORDER BY event_id",
    )
    intermediate_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id FROM __loader__fetch_events ORDER BY event_id",
    )
    assert tuple(rows) == test_case.expected_rows
    assert tuple(intermediate_rows) == ((1,), (2,))


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderSchemaEvolutionE2ETestCase(
            description="run auto-loads intermediate loader dependencies",
            command=("--no-color", "run", "--select", "+fact_events"),
            expected_rows=((1, "loaded"), (2, "loaded")),
        )
    ],
    ids=["run auto-loads intermediate loader dependencies"],
)
def test_given_chained_loader_project_when_running_source_model_then_runs_loader_dag(
    tmp_path: Path,
    test_case: SourceLoaderSchemaEvolutionE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    loader: raw_events\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                "        type: VARCHAR\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    return [{'event_id': 1}, {'event_id': 2}]\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                "SELECT event_id, 'loaded' AS status FROM {events.target}\")\n"
            ),
        )
        | {
            "models/fact_events.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT event_id, status FROM __source("raw_events")\n'
            )
        },
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert "loader    fetch_events" in result.stdout
    assert "source    raw_events" in result.stdout
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, status FROM fact_events ORDER BY event_id",
    )
    intermediate_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id FROM __loader__fetch_events ORDER BY event_id",
    )
    assert tuple(rows) == test_case.expected_rows
    assert tuple(intermediate_rows) == ((1,), (2,))


CHAINED_LOADER_SELECTION_TEST_CASES: list[ChainedLoaderSelectionE2ETestCase] = [
    ChainedLoaderSelectionE2ETestCase(
        description="direct intermediate selection loads only the intermediate target",
        command=("--no-color", "load", "--select", "fetch_events"),
        expected_raw_events_exists=False,
        expected_intermediate_rows=((1, 1), (2, 1)),
        expected_stdout_fragments=(
            "Loaders (1)",
            "  fetch_events",
            "loader    fetch_events",
            "Sources (0)",
        ),
    ),
    ChainedLoaderSelectionE2ETestCase(
        description="leading plus source selection includes upstream intermediate",
        command=("--no-color", "load", "--select", "+raw_events"),
        expected_raw_events_exists=True,
        expected_intermediate_rows=((1, 1), (2, 1)),
        expected_stdout_fragments=(
            "Loaders (1)",
            "  fetch_events",
            "loader    fetch_events",
            "Sources (1)",
            "source    raw_events",
        ),
    ),
    ChainedLoaderSelectionE2ETestCase(
        description="trailing plus includes downstream terminal source",
        command=("--no-color", "load", "--select", "fetch_events+"),
        expected_raw_events_exists=True,
        expected_intermediate_rows=((1, 1), (2, 1)),
        expected_stdout_fragments=(
            "Loaders (1)",
            "  fetch_events",
            "loader    fetch_events",
            "Sources (1)",
            "source    raw_events",
        ),
    ),
    ChainedLoaderSelectionE2ETestCase(
        description="both sided plus includes upstream and downstream load graph",
        command=("--no-color", "load", "--select", "+fetch_events+"),
        expected_raw_events_exists=True,
        expected_intermediate_rows=((1, 1), (2, 1)),
        expected_stdout_fragments=(
            "Loaders (1)",
            "  fetch_events",
            "loader    fetch_events",
            "Sources (1)",
            "source    raw_events",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CHAINED_LOADER_SELECTION_TEST_CASES,
    ids=[case.description for case in CHAINED_LOADER_SELECTION_TEST_CASES],
)
def test_given_chained_loader_project_when_selecting_loader_then_expands_expected_nodes(
    tmp_path: Path,
    test_case: ChainedLoaderSelectionE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=("sources:\n  - name: raw_events\n    loader: raw_events\n"),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    return [{'event_id': 1, 'load_seq': 1}, {'event_id': 2, 'load_seq': 1}]\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                'SELECT event_id FROM {events.target}")\n'
            ),
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    intermediate_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, load_seq FROM __loader__fetch_events ORDER BY event_id",
    )
    assert tuple(intermediate_rows) == test_case.expected_intermediate_rows
    assert table_exists(db_path=db_path, table_name="raw_events") is (
        test_case.expected_raw_events_exists
    )


CHAINED_LOADER_PRUNING_TEST_CASES: list[ChainedLoaderPruningE2ETestCase] = [
    ChainedLoaderPruningE2ETestCase(
        description="excluding required intermediate prunes terminal source",
        command=("--no-color", "load", "--select", "raw_events", "--exclude", "fetch_events"),
        expected_raw_events_exists=False,
        expected_intermediate_exists=False,
    ),
    ChainedLoaderPruningE2ETestCase(
        description="excluding downstream from intermediate prunes terminal source",
        command=(
            "--no-color",
            "load",
            "--select",
            "fetch_events+",
            "--exclude",
            "fetch_events+",
        ),
        expected_raw_events_exists=False,
        expected_intermediate_exists=False,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CHAINED_LOADER_PRUNING_TEST_CASES,
    ids=[case.description for case in CHAINED_LOADER_PRUNING_TEST_CASES],
)
def test_given_chained_loader_project_when_excluding_dependency_then_prunes_dependents(
    tmp_path: Path,
    test_case: ChainedLoaderPruningE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=("sources:\n  - name: raw_events\n    loader: raw_events\n"),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    return [{'event_id': 1}]\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                'SELECT event_id FROM {events.target}")\n'
            ),
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert (db_path.exists() and table_exists(db_path=db_path, table_name="raw_events")) is (
        test_case.expected_raw_events_exists
    )
    assert (
        db_path.exists() and table_exists(db_path=db_path, table_name="__loader__fetch_events")
    ) is (test_case.expected_intermediate_exists)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceLoaderSchemaEvolutionE2ETestCase(
            description="custom intermediate target is used by downstream loader refs",
            command=("--no-color", "load", "--select", "raw_events"),
            expected_rows=((1, "custom_fetch_events"),),
        )
    ],
    ids=["custom intermediate target is used by downstream loader refs"],
)
def test_given_chained_loader_project_when_intermediate_has_custom_target_then_refs_resolve(
    tmp_path: Path,
    test_case: SourceLoaderSchemaEvolutionE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=("sources:\n  - name: raw_events\n    loader: raw_events\n"),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(target='custom_fetch_events', write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    return [{'event_id': 1}]\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                "SELECT event_id, '{events.table_name}' AS source_table FROM {events.target}\")\n"
            ),
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, source_table FROM raw_events ORDER BY event_id",
    )
    custom_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id FROM custom_fetch_events ORDER BY event_id",
    )
    assert tuple(rows) == test_case.expected_rows
    assert tuple(custom_rows) == ((1,),)


INTERMEDIATE_LOADER_STRATEGY_TEST_CASES: list[IntermediateLoaderStrategyE2ETestCase] = [
    IntermediateLoaderStrategyE2ETestCase(
        description="append intermediate accumulates rows across DAG loads",
        loader_py=(
            "from sqlbuild.loaders import loader\n\n"
            "@loader(write_strategy='append', columns=[\n"
            "    {'name': 'event_id', 'type': 'INTEGER'},\n"
            "    {'name': 'amount', 'type': 'INTEGER'},\n"
            "])\n"
            "def fetch_events(ctx):\n"
            "    return [{'event_id': 1, 'amount': 100}, {'event_id': 2, 'amount': 200}]\n\n"
            "@loader(depends_on=[fetch_events])\n"
            "def raw_events(ctx):\n"
            "    events = ctx.loader(fetch_events)\n"
            "    cursor = ctx.query(\n"
            "        f'SELECT event_id, amount FROM {events.target} ORDER BY event_id, amount'\n"
            "    )\n"
            "    rows = cursor.fetchall()\n"
            "    return [{'event_id': row[0], 'amount': row[1]} for row in rows]\n"
        ),
        expected_intermediate_rows=((1, 100), (1, 100), (2, 200), (2, 200)),
        expected_terminal_rows=((1, 100), (1, 100), (2, 200), (2, 200)),
    ),
    IntermediateLoaderStrategyE2ETestCase(
        description="merge intermediate remains keyed across DAG loads",
        loader_py=(
            "from sqlbuild.loaders import loader\n\n"
            "@loader(\n"
            "    write_strategy='merge',\n"
            "    unique_key='event_id',\n"
            "    cursor_column='load_seq',\n"
            "    columns=[\n"
            "    {'name': 'event_id', 'type': 'INTEGER'},\n"
            "    {'name': 'amount', 'type': 'INTEGER'},\n"
            "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
            "])\n"
            "def fetch_events(ctx):\n"
            "    if ctx.current_cursor_value is None:\n"
            "        return [\n"
            "            {'event_id': 1, 'amount': 100, 'load_seq': 1},\n"
            "            {'event_id': 2, 'amount': 200, 'load_seq': 1},\n"
            "        ]\n"
            "    return [\n"
            "        {'event_id': 1, 'amount': 150, 'load_seq': 2},\n"
            "        {'event_id': 3, 'amount': 300, 'load_seq': 2},\n"
            "    ]\n\n"
            "@loader(depends_on=[fetch_events])\n"
            "def raw_events(ctx):\n"
            "    events = ctx.loader(fetch_events)\n"
            "    cursor = ctx.query(\n"
            "        f'SELECT event_id, amount FROM {events.target} ORDER BY event_id, amount'\n"
            "    )\n"
            "    rows = cursor.fetchall()\n"
            "    return [{'event_id': row[0], 'amount': row[1]} for row in rows]\n"
        ),
        expected_intermediate_rows=((1, 150), (2, 200), (3, 300)),
        expected_terminal_rows=((1, 150), (2, 200), (3, 300)),
    ),
    IntermediateLoaderStrategyE2ETestCase(
        description="delete insert intermediate is idempotent across DAG loads",
        loader_py=(
            "from sqlbuild.loaders import loader\n\n"
            "@loader(write_strategy='delete_insert', cursor_column='load_seq', columns=[\n"
            "    {'name': 'event_id', 'type': 'INTEGER'},\n"
            "    {'name': 'amount', 'type': 'INTEGER'},\n"
            "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
            "])\n"
            "def fetch_events(ctx):\n"
            "    if ctx.current_cursor_value is not None:\n"
            "        return [\n"
            "            {'event_id': 2, 'amount': 250, 'load_seq': 1},\n"
            "            {'event_id': 3, 'amount': 300, 'load_seq': 1},\n"
            "        ]\n"
            "    return [\n"
            "        {'event_id': 1, 'amount': 100, 'load_seq': 1},\n"
            "        {'event_id': 2, 'amount': 200, 'load_seq': 1},\n"
            "    ]\n\n"
            "@loader(depends_on=[fetch_events])\n"
            "def raw_events(ctx):\n"
            "    events = ctx.loader(fetch_events)\n"
            "    cursor = ctx.query(\n"
            "        f'SELECT event_id, amount FROM {events.target} ORDER BY event_id, amount'\n"
            "    )\n"
            "    rows = cursor.fetchall()\n"
            "    return [{'event_id': row[0], 'amount': row[1]} for row in rows]\n"
        ),
        expected_intermediate_rows=((2, 250), (3, 300)),
        expected_terminal_rows=((2, 250), (3, 300)),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    INTERMEDIATE_LOADER_STRATEGY_TEST_CASES,
    ids=[case.description for case in INTERMEDIATE_LOADER_STRATEGY_TEST_CASES],
)
def test_given_chained_loader_project_when_intermediate_uses_strategy_then_applies_strategy(
    tmp_path: Path,
    test_case: IntermediateLoaderStrategyE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    loader: raw_events\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: amount\n"
                "        type: INTEGER\n"
            ),
            loader_py=test_case.loader_py,
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    second_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert first_result.returncode == test_case.expected_return_code, (
        first_result.stdout + first_result.stderr
    )
    assert second_result.returncode == test_case.expected_return_code, (
        second_result.stdout + second_result.stderr
    )
    intermediate_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=("SELECT event_id, amount FROM __loader__fetch_events ORDER BY event_id, amount"),
    )
    terminal_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, amount FROM raw_events ORDER BY event_id, amount",
    )
    assert tuple(intermediate_rows) == test_case.expected_intermediate_rows
    assert tuple(terminal_rows) == test_case.expected_terminal_rows


@pytest.mark.parametrize(
    "test_case",
    [
        ChainedLoaderFailureE2ETestCase(
            description=(
                "failed intermediate skips dependent source but independent branch continues"
            ),
            command=("--no-color", "load"),
            expected_ok_rows=((1,),),
            expected_error_fragment="boom",
            expected_skip_fragment="FAIL=1  SKIP=1",
        )
    ],
    ids=["failed intermediate skips dependent source but independent branch continues"],
)
def test_given_loader_dependency_failure_when_loading_then_only_dependents_skip(
    tmp_path: Path,
    test_case: ChainedLoaderFailureE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_bad\n"
                "    loader: raw_bad\n"
                "  - name: raw_ok\n"
                "    loader: raw_ok\n"
                "    write_strategy: table\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_bad(ctx):\n"
                "    raise RuntimeError('boom')\n\n"
                "@loader(depends_on=[fetch_bad])\n"
                "def raw_bad(ctx):\n"
                "    events = ctx.loader(fetch_bad)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                'SELECT event_id FROM {events.target}")\n\n'
                "@loader\n"
                "def raw_ok(ctx):\n"
                "    return [{'event_id': 1}]\n"
            ),
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in result.stdout
    assert test_case.expected_skip_fragment in result.stdout
    ok_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id FROM raw_ok ORDER BY event_id",
    )
    assert tuple(ok_rows) == test_case.expected_ok_rows
    assert table_exists(db_path=db_path, table_name="raw_bad") is False


@pytest.mark.parametrize(
    "test_case",
    [
        ChainedLoaderFailureE2ETestCase(
            description="build skips models dependent on failed loader branch only",
            command=("--no-color", "build", "--select", "+bad_model", "--select", "+ok_model"),
            expected_ok_rows=((1,),),
            expected_error_fragment="boom",
            expected_skip_fragment="SKIP",
        )
    ],
    ids=["build skips models dependent on failed loader branch only"],
)
def test_given_loader_dependency_failure_when_building_then_only_dependents_skip(
    tmp_path: Path,
    test_case: ChainedLoaderFailureE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_bad\n"
                "    loader: raw_bad\n"
                "  - name: raw_ok\n"
                "    loader: raw_ok\n"
                "    write_strategy: table\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_bad(ctx):\n"
                "    raise RuntimeError('boom')\n\n"
                "@loader(depends_on=[fetch_bad])\n"
                "def raw_bad(ctx):\n"
                "    events = ctx.loader(fetch_bad)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                'SELECT event_id FROM {events.target}")\n\n'
                "@loader\n"
                "def raw_ok(ctx):\n"
                "    return [{'event_id': 1}]\n"
            ),
        )
        | {
            "models/bad_model.sql": (
                'MODEL (materialized table);\n\nSELECT event_id FROM __source("raw_bad")\n'
            ),
            "models/ok_model.sql": (
                'MODEL (materialized table);\n\nSELECT event_id FROM __source("raw_ok")\n'
            ),
        },
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in result.stdout
    assert test_case.expected_skip_fragment in result.stdout
    assert "ok_model" in result.stdout
    assert "bad_model" in result.stdout
    ok_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id FROM ok_model ORDER BY event_id",
    )
    assert tuple(ok_rows) == test_case.expected_ok_rows
    assert table_exists(db_path=db_path, table_name="bad_model") is False


@pytest.mark.parametrize(
    "test_case",
    [
        ChainedLoaderFailureE2ETestCase(
            description="json output includes skipped dependent loader result",
            command=("--no-color", "load", "--json"),
            expected_ok_rows=((1,),),
            expected_error_fragment="boom",
            expected_skip_fragment="skipped",
        )
    ],
    ids=["json output includes skipped dependent loader result"],
)
def test_given_loader_dependency_failure_when_loading_json_then_reports_skipped_asset(
    tmp_path: Path,
    test_case: ChainedLoaderFailureE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_bad\n"
                "    loader: raw_bad\n"
                "  - name: raw_ok\n"
                "    loader: raw_ok\n"
                "    write_strategy: table\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_bad(ctx):\n"
                "    raise RuntimeError('boom')\n\n"
                "@loader(depends_on=[fetch_bad])\n"
                "def raw_bad(ctx):\n"
                "    events = ctx.loader(fetch_bad)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                'SELECT event_id FROM {events.target}")\n\n'
                "@loader\n"
                "def raw_ok(ctx):\n"
                "    return [{'event_id': 1}]\n"
            ),
        ),
    )
    db_path: Path = project_dir / "source_loader_schema_behavior.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    payload: dict[str, object] = json.loads(result.stdout)
    assets: list[dict[str, object]] = list(payload["assets"])
    statuses_by_name: dict[str, object] = {str(asset["name"]): asset["status"] for asset in assets}
    summary: dict[str, object] = dict(payload["summary"])
    assert statuses_by_name["fetch_bad"] == "failed"
    assert statuses_by_name["raw_bad"] == test_case.expected_skip_fragment
    assert statuses_by_name["raw_ok"] == "success"
    assert summary["skipped_count"] == 1
    ok_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT event_id FROM raw_ok ORDER BY event_id",
    )
    assert tuple(ok_rows) == test_case.expected_ok_rows


SOURCE_LOADER_ERROR_TEST_CASES: list[SourceLoaderErrorE2ETestCase] = [
    SourceLoaderErrorE2ETestCase(
        description="contract rejects extra returned columns",
        command=("--no-color", "load"),
        expected_error_fragment="contract has extra columns: extra_note",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_contract_events\n"
                "    loader: raw_contract_events\n"
                "    write_strategy: table\n"
                "    contract: enforced\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_contract_events(ctx):\n"
                "    return [{'event_id': 1, 'extra_note': 'not declared'}]\n"
            ),
        ),
    ),
    SourceLoaderErrorE2ETestCase(
        description="contract rejects missing declared columns",
        command=("--no-color", "load"),
        expected_error_fragment="contract missing columns: event_name",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_contract_events\n"
                "    loader: raw_contract_events\n"
                "    write_strategy: table\n"
                "    contract: enforced\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: event_name\n"
                "        type: VARCHAR\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_contract_events(ctx):\n"
                "    return [{'event_id': 1}]\n"
            ),
        ),
    ),
    SourceLoaderErrorE2ETestCase(
        description="existing target rejects returned type changes",
        command=("--no-color", "load"),
        expected_error_fragment="column 'amount' changed type",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n"
                "    loader: raw_events\n"
                "    write_strategy: append\n"
                "    cursor_column: load_seq\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: load_seq\n"
                "        type: INTEGER\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_events(ctx):\n"
                "    if ctx.current_cursor_value is None:\n"
                "        return [{'event_id': 1, 'load_seq': 1, 'amount': 100}]\n"
                "    return [{'event_id': 2, 'load_seq': 2, 'amount': 'one hundred'}]\n"
            ),
        ),
    ),
    SourceLoaderErrorE2ETestCase(
        description="intermediate contract rejects extra returned columns",
        command=("--no-color", "load", "--select", "raw_events"),
        expected_error_fragment="contract has extra columns: extra_note",
        repo_files=build_schema_behavior_project_files(
            source_yaml=("sources:\n  - name: raw_events\n    loader: raw_events\n"),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', contract='enforced', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    return [{'event_id': 1, 'extra_note': 'not declared'}]\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                'SELECT event_id FROM {events.target}")\n'
            ),
        ),
    ),
    SourceLoaderErrorE2ETestCase(
        description="self managed intermediate without target fails",
        command=("--no-color", "load", "--select", "raw_events"),
        expected_error_fragment="returned no rows and has no target declared",
        repo_files=build_schema_behavior_project_files(
            source_yaml=("sources:\n  - name: raw_events\n    loader: raw_events\n"),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def fetch_events(ctx):\n"
                "    ctx.execute_sql('SELECT 1')\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    events = ctx.loader(fetch_events)\n"
                '    ctx.execute_sql(f"CREATE OR REPLACE TABLE {ctx.target} AS '
                'SELECT * FROM {events.target}")\n'
            ),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SOURCE_LOADER_ERROR_TEST_CASES,
    ids=[case.description for case in SOURCE_LOADER_ERROR_TEST_CASES],
)
def test_given_loader_schema_error_when_loading_then_reports_expected_failure(
    tmp_path: Path,
    test_case: SourceLoaderErrorE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=test_case.repo_files,
    )

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert first_result.returncode in {0, test_case.expected_return_code}, (
        first_result.stdout + first_result.stderr
    )
    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in result.stdout
