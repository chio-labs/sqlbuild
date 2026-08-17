"""E2E tests for sqb clone command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clone._test_types import (
    CloneE2ETestCase,
    ClonePolicyErrorTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneE2ETestCase(
            description="clone uses active destination copies tables and recreates views",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                    name = "clone_project"
                    adapter = "duckdb"
                    default_target = "dev"

                    [targets.prod]
                    schema = "prod"

                    [targets.prod.connection]
                    database = "clone.duckdb"

                    [targets.prod.clone]
                    allow_as_clone_origin = true
                    allow_as_clone_destination = false

                    [targets.dev]
                    schema = "dev"

                    [targets.dev.connection]
                    database = "clone.duckdb"

                    [targets.dev.clone]
                    allow_as_clone_origin = true
                    allow_as_clone_destination = true
                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_orders
                        expression: |
                          SELECT *
                          FROM (VALUES (1, 100), (2, 200))
                            AS raw_orders(order_id, amount_cents)
                    """
                ).strip()
                + "\n",
                "models/fact_orders.sql": dedent(
                    """
                    MODEL (materialized table);

                    SELECT order_id, amount_cents FROM __source("raw_orders")
                    """
                ).strip()
                + "\n",
                "models/orders_enriched.sql": dedent(
                    """
                    MODEL (materialized view);

                    SELECT order_id, amount_cents, amount_cents * 2 AS doubled_cents
                    FROM __ref("fact_orders")
                    """
                ).strip()
                + "\n",
                "models/missing_snapshot.sql": dedent(
                    """
                    MODEL (materialized table);

                    SELECT 1 AS id
                    """
                ).strip()
                + "\n",
            },
            clone_command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--select",
                "fact_orders",
                "orders_enriched",
                "missing_snapshot",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "fact_orders",
                "copied",
                "orders_enriched",
                "recreated_view",
                "missing_snapshot",
                "missing in origin environment",
                "\u2713 Completed with warnings",
                "WARN=1",
            ),
            expected_query_results=(
                (
                    "SELECT order_id, amount_cents FROM dev.fact_orders ORDER BY order_id",
                    ((1, 100), (2, 200)),
                ),
                (
                    "SELECT order_id, doubled_cents FROM dev.orders_enriched ORDER BY order_id",
                    ((1, 200), (2, 400)),
                ),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_command_when_running_then_managed_relations_sync_as_expected(
    test_case: CloneE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="clone_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "clone.duckdb"

    import duckdb

    prod_connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    prod_connection.execute("CREATE SCHEMA prod")
    prod_connection.execute("CREATE SCHEMA dev")
    prod_connection.execute(
        "CREATE TABLE prod.fact_orders AS "
        "SELECT * FROM (VALUES (1, 100), (2, 200)) AS t(order_id, amount_cents)"
    )
    prod_connection.execute(
        "CREATE OR REPLACE VIEW prod.orders_enriched AS "
        "SELECT order_id, amount_cents, amount_cents * 2 AS doubled_cents "
        "FROM prod.fact_orders"
    )
    prod_connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.clone_command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr

    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        actual_rows: list[tuple[object, ...]] = query_duckdb(db_path=db_path, sql=query)
        assert tuple(tuple(row) for row in actual_rows) == expected_rows


@pytest.mark.parametrize(
    "test_case",
    (
        CloneE2ETestCase(
            description="clone copies managed source before recreating dependent view",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                    name = "managed_source_clone_project"
                    adapter = "duckdb"
                    default_target = "dev"

                    [targets.dev]
                    schema = "dev"
                    loader_schema = "raw_dev"

                    [targets.dev.connection]
                    database = "clone.duckdb"

                    [targets.dev.clone]
                    allow_as_clone_origin = true

                    [targets.prod]
                    schema = "prod"
                    loader_schema = "raw_prod"

                    [targets.prod.connection]
                    database = "clone.duckdb"

                    [targets.prod.clone]
                    allow_as_clone_destination = true
                    """
                ).strip()
                + "\n",
                "loaders/raw.py": dedent(
                    """
                    from sqlbuild.loaders import loader

                    @loader
                    def raw_customers(ctx):
                        return []
                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_customers
                        managed: true
                        write_strategy: table
                        columns:
                          - name: customer_id
                            type: INTEGER
                          - name: first_name
                            type: VARCHAR
                    """
                ).strip()
                + "\n",
                "models/stg_customers.sql": dedent(
                    """
                    MODEL (materialized view);

                    SELECT customer_id, first_name FROM __source("raw_customers")
                    """
                ).strip()
                + "\n",
            },
            clone_command=("--no-color", "clone", "--from", "dev", "--to", "prod"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "raw_customers",
                "copied",
                "stg_customers",
                "recreated_view",
            ),
            expected_query_results=(
                (
                    "SELECT customer_id, first_name FROM prod.stg_customers ORDER BY customer_id",
                    ((1, "Ada"), (2, "Grace")),
                ),
            ),
        ),
        CloneE2ETestCase(
            description="clone preserves destination deferral without copying managed source",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                    name = "managed_source_clone_project"
                    adapter = "duckdb"
                    default_target = "dev"

                    [targets.dev]
                    schema = "dev"
                    loader_schema = "raw_dev"

                    [targets.dev.connection]
                    database = "clone.duckdb"

                    [targets.dev.clone]
                    allow_as_clone_origin = true

                    [targets.prod]
                    schema = "prod"
                    loader_schema = "raw_prod"
                    defer_sources_to = "dev"

                    [targets.prod.connection]
                    database = "clone.duckdb"

                    [targets.prod.clone]
                    allow_as_clone_destination = true
                    """
                ).strip()
                + "\n",
                "loaders/raw.py": dedent(
                    """
                    from sqlbuild.loaders import loader

                    @loader
                    def raw_customers(ctx):
                        return []
                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_customers
                        managed: true
                        write_strategy: table
                        columns:
                          - name: customer_id
                            type: INTEGER
                          - name: first_name
                            type: VARCHAR
                    """
                ).strip()
                + "\n",
                "models/stg_customers.sql": dedent(
                    """
                    MODEL (materialized view);

                    SELECT customer_id, first_name FROM __source("raw_customers")
                    """
                ).strip()
                + "\n",
            },
            clone_command=("--no-color", "clone", "--from", "dev", "--to", "prod"),
            expected_exit_code=0,
            expected_stdout_fragments=("stg_customers", "recreated_view"),
            expected_query_results=(
                (
                    "SELECT customer_id, first_name FROM prod.stg_customers ORDER BY customer_id",
                    ((1, "Ada"), (2, "Grace")),
                ),
                (
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'raw_prod' AND table_name = 'raw_customers'",
                    ((0,),),
                ),
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_managed_source_when_cloning_then_source_routing_is_preserved(
    test_case: CloneE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="managed_source_clone_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "clone.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute("CREATE SCHEMA dev")
    connection.execute("CREATE SCHEMA prod")
    connection.execute("CREATE SCHEMA raw_dev")
    connection.execute("CREATE SCHEMA raw_prod")
    connection.execute(
        "CREATE TABLE raw_dev.raw_customers AS "
        "SELECT * FROM (VALUES (1, 'Ada'), (2, 'Grace')) AS t(customer_id, first_name)"
    )
    connection.execute(
        "CREATE VIEW dev.stg_customers AS SELECT customer_id, first_name FROM raw_dev.raw_customers"
    )
    connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.clone_command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr
    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        actual_rows: list[tuple[object, ...]] = query_duckdb(db_path=db_path, sql=query)
        assert tuple(tuple(row) for row in actual_rows) == expected_rows


@pytest.mark.parametrize(
    "test_case",
    (
        ClonePolicyErrorTestCase(
            description="denied origin identifies its enabling policy",
            origin_allowed=False,
            destination_allowed=True,
            expected_error_code="C404",
            expected_policy_key="targets.prod.clone.allow_as_clone_origin = true",
        ),
        ClonePolicyErrorTestCase(
            description="denied destination identifies its enabling policy",
            origin_allowed=True,
            destination_allowed=False,
            expected_error_code="C405",
            expected_policy_key="targets.dev.clone.allow_as_clone_destination = true",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_denied_clone_policy_when_running_then_error_identifies_configuration_fix(
    test_case: ClonePolicyErrorTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="clone_policy_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                f"""
                name = "clone_policy_project"
                adapter = "duckdb"
                default_target = "dev"

                [targets.prod]
                schema = "prod"

                [targets.prod.clone]
                allow_as_clone_origin = {str(test_case.origin_allowed).lower()}

                [targets.dev]
                schema = "dev"

                [targets.dev.clone]
                allow_as_clone_destination = {str(test_case.destination_allowed).lower()}
                """
            ).strip()
            + "\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "clone", "--from", "prod", "--to", "dev"),
        project_dir=project_dir,
    )
    combined_output: str = result.stdout + result.stderr

    assert result.returncode != 0
    assert test_case.expected_error_code in combined_output
    assert test_case.expected_policy_key in combined_output
