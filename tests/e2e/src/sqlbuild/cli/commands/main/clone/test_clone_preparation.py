"""E2E coverage for which resources sqb clone prepares, where they go, and its terminal output."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clone._test_types import (
    ClonePreparationE2ETestCase,
    CloneTerminalProgressE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    SPINNER_GLYPHS,
    assert_fragments_in_order,
    prepare_inline_project,
    query_duckdb,
    render_terminal_screen,
    run_sqb,
    run_sqb_with_pty,
)

_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": dedent(
        """
        name = "clone_preparation_project"
        adapter = "duckdb"
        default_target = "dev"

        [connections.local]
        database = "clone.duckdb"

        [targets.prod]
        schema = "prod"
        loader_schema = "raw_prod"

        [targets.prod.vars]
        region = "emea"

        [targets.prod.clone]
        allow_as_clone_origin = true

        [targets.dev]
        schema = "dev"
        loader_schema = "raw_dev"

        [targets.dev.vars]
        region = "apac"

        [targets.dev.clone]
        allow_as_clone_destination = true

        [targets.review]
        schema = "review"
        loader_schema = "raw_review"
        defer_sources_to = "prod"

        [targets.review.vars]
        region = "amer"

        [targets.review.clone]
        allow_as_clone_destination = true
        """
    ).lstrip(),
    "python/loaders/raw.py": dedent(
        """
        from sqlbuild.loaders import loader


        @loader
        def raw_payments(ctx):
            '''Test loader raw_payments.'''
            return [{"payment_id": 1, "order_id": 1, "amount_cents": 500}]
        """
    ).lstrip(),
    "sources/raw.yml": dedent(
        """
        sources:
          - name: raw_payments
            description: Test source raw_payments.
            managed: true
            write_strategy: table
            columns:
              - name: payment_id
                type: INTEGER
              - name: order_id
                type: INTEGER
              - name: amount_cents
                type: INTEGER
          - name: raw_orders
            description: Test source raw_orders.
            expression: |
              SELECT *
              FROM (VALUES (1, 101, 100), (2, 102, 200))
                AS raw_orders(order_id, customer_id, amount_cents)
        """
    ).lstrip(),
    "seeds/customers.csv": "customer_id,customer_name\n101,Ada\n102,Grace\n",
    "seeds/schema.yml": dedent(
        """
        seeds:
          - name: customers
            description: Test seed customers.
            columns:
              - name: customer_id
                type: INTEGER
              - name: customer_name
                type: VARCHAR
        """
    ).lstrip(),
    "models/staging/stg_orders.sql": dedent(
        """
        MODEL (description "Test model stg_orders.", materialized view);

        SELECT order_id, customer_id, amount_cents, '@@region' AS region FROM __source("raw_orders")
        """
    ).lstrip(),
    "models/staging/stg_payments.sql": dedent(
        """
        MODEL (description "Test model stg_payments.", materialized view);

        SELECT * FROM __source("raw_payments")
        """
    ).lstrip(),
    "models/marts/fct_orders.sql": dedent(
        """
        MODEL (description "Test model fct_orders.", materialized table);

        SELECT o.order_id, o.amount_cents, c.customer_name
        FROM __ref("stg_orders") AS o
        JOIN __seed("customers") AS c ON c.customer_id = o.customer_id
        """
    ).lstrip(),
    "models/marts/fct_order_events.sql": dedent(
        """
        MODEL (
          description "Test model fct_order_events.",
          materialized incremental,
          incremental_strategy append
        );

        SELECT order_id, amount_cents FROM __ref("fct_orders")
        """
    ).lstrip(),
    "models/marts/orders_summary.sql": dedent(
        """
        MODEL (description "Test model orders_summary.", materialized view);

        SELECT f.*, p.amount_cents AS paid_cents
        FROM __ref("fct_orders") AS f
        LEFT JOIN __ref("stg_payments") AS p ON p.order_id = f.order_id
        """
    ).lstrip(),
    "models/marts/orders_backlog.sql": dedent(
        """
        MODEL (description "Test model orders_backlog.", materialized table);

        SELECT order_id FROM __ref("fct_orders") WHERE amount_cents > 150
        """
    ).lstrip(),
    "models/marts/retired_orders.sql": dedent(
        """
        MODEL (description "Test model retired_orders.", materialized table, enabled false);

        SELECT order_id FROM __ref("fct_orders")
        """
    ).lstrip(),
    "functions/sql/cents_to_units.sql": dedent(
        """
        FUNCTION (description "Test function cents_to_units.", arguments (amount INTEGER), returns DOUBLE);

        amount / 100.0
        """
    ).lstrip(),
}

_VIEW_ROWS: str = (
    "SELECT schema_name, view_name, sql FROM duckdb_views() "
    "WHERE NOT internal AND schema_name = '{schema}' ORDER BY view_name"
)
_DEV_VIEWS: tuple[tuple[object, ...], ...] = (
    (
        "dev",
        "orders_summary",
        "CREATE VIEW dev.orders_summary AS SELECT f.*, p.amount_cents AS paid_cents "
        "FROM dev.fct_orders AS f LEFT JOIN dev.stg_payments AS p "
        "ON ((p.order_id = f.order_id));",
    ),
    (
        "dev",
        "stg_orders",
        "CREATE VIEW dev.stg_orders AS SELECT order_id, customer_id, amount_cents, "
        "'apac' AS region FROM (SELECT * FROM (SELECT * FROM (VALUES (1, 101, 100), "
        "(2, 102, 200)) AS valueslist) AS raw_orders(order_id, customer_id, amount_cents));",
    ),
    ("dev", "stg_payments", "CREATE VIEW dev.stg_payments AS SELECT * FROM raw_dev.raw_payments;"),
)


def _asset(
    kind: str, name: str, action: str, origin: str | None, target: str
) -> tuple[str, str, str, str | None, str]:
    return (kind, name, action, origin, target)


_ALL_DEV_ASSETS: tuple[tuple[str, str, str, str | None, str], ...] = (
    _asset("seed", "customers", "copied", "prod.customers", "dev.customers"),
    _asset("model", "stg_orders", "recreated_view", "prod.stg_orders", "dev.stg_orders"),
    _asset("model", "fct_orders", "copied", "prod.fct_orders", "dev.fct_orders"),
    _asset("model", "fct_order_events", "copied", "prod.fct_order_events", "dev.fct_order_events"),
    _asset(
        "model",
        "orders_backlog",
        "warning_missing_source",
        "prod.orders_backlog",
        "dev.orders_backlog",
    ),
    _asset("source", "raw_payments", "copied", "raw_prod.raw_payments", "raw_dev.raw_payments"),
    _asset("model", "stg_payments", "recreated_view", "prod.stg_payments", "dev.stg_payments"),
    _asset(
        "model", "orders_summary", "recreated_view", "prod.orders_summary", "dev.orders_summary"
    ),
    _asset("udf", "cents_to_units", "recreated_function", None, "dev.cents_to_units"),
)


def _prepare_origin(tmp_path: Path) -> Path:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="clone_preparation_project", repo_files=_PROJECT_FILES
    )
    for command in (
        ("--no-color", "load", "--target", "prod"),
        ("--no-color", "build", "--target", "prod", "--exclude", "orders_backlog"),
    ):
        result: subprocess.CompletedProcess[str] = run_sqb(command=command, project_dir=project_dir)
        assert result.returncode == 0, result.stdout + result.stderr
    return project_dir


@pytest.fixture(scope="module")
def origin_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A project whose prod target is built, except `orders_backlog`, shared read-only."""

    return _prepare_origin(tmp_path_factory.mktemp("clone_preparation_origin"))


def _project_copy(*, origin_project: Path, tmp_path: Path) -> Path:
    project_dir: Path = tmp_path / origin_project.name
    shutil.copytree(origin_project, project_dir)
    return project_dir


@pytest.mark.parametrize(
    "test_case",
    (
        ClonePreparationE2ETestCase(
            description="whole project clones in graph order and reports the missing origin",
            clone_arguments=("--from", "prod", "--to", "dev"),
            expected_assets=_ALL_DEV_ASSETS,
            expected_query_results=(
                (_VIEW_ROWS.format(schema="dev"), _DEV_VIEWS),
                ("SELECT DISTINCT region FROM dev.stg_orders", (("apac",),)),
                (
                    "SELECT order_id, paid_cents FROM dev.orders_summary ORDER BY order_id",
                    ((1, 500), (2, None)),
                ),
            ),
        ),
        ClonePreparationE2ETestCase(
            description="graph selector clones the selected view and its ancestors",
            clone_arguments=("--from", "prod", "--to", "dev", "--select", "+orders_summary"),
            expected_assets=(
                _ALL_DEV_ASSETS[0],
                _ALL_DEV_ASSETS[1],
                _ALL_DEV_ASSETS[2],
                _ALL_DEV_ASSETS[5],
                _ALL_DEV_ASSETS[6],
                _ALL_DEV_ASSETS[7],
            ),
            expected_query_results=((_VIEW_ROWS.format(schema="dev"), _DEV_VIEWS),),
        ),
        ClonePreparationE2ETestCase(
            description="excluded view and seed are left out",
            clone_arguments=(
                "--from",
                "prod",
                "--to",
                "dev",
                "--exclude",
                "orders_summary",
                "customers",
            ),
            expected_assets=(
                _ALL_DEV_ASSETS[1],
                _ALL_DEV_ASSETS[2],
                _ALL_DEV_ASSETS[3],
                _ALL_DEV_ASSETS[4],
                _ALL_DEV_ASSETS[5],
                _ALL_DEV_ASSETS[6],
                _ALL_DEV_ASSETS[8],
            ),
            expected_query_results=(
                (_VIEW_ROWS.format(schema="dev"), (_DEV_VIEWS[1], _DEV_VIEWS[2])),
            ),
        ),
        ClonePreparationE2ETestCase(
            description="destination deferring sources reads origin sources and skips them",
            clone_arguments=("--from", "prod", "--to", "review"),
            expected_assets=(
                _asset("seed", "customers", "copied", "prod.customers", "review.customers"),
                _asset(
                    "model", "stg_orders", "recreated_view", "prod.stg_orders", "review.stg_orders"
                ),
                _asset("model", "fct_orders", "copied", "prod.fct_orders", "review.fct_orders"),
                _asset(
                    "model",
                    "fct_order_events",
                    "copied",
                    "prod.fct_order_events",
                    "review.fct_order_events",
                ),
                _asset(
                    "model",
                    "orders_backlog",
                    "warning_missing_source",
                    "prod.orders_backlog",
                    "review.orders_backlog",
                ),
                _asset(
                    "model",
                    "stg_payments",
                    "recreated_view",
                    "prod.stg_payments",
                    "review.stg_payments",
                ),
                _asset(
                    "model",
                    "orders_summary",
                    "recreated_view",
                    "prod.orders_summary",
                    "review.orders_summary",
                ),
                _asset(
                    "udf", "cents_to_units", "recreated_function", None, "review.cents_to_units"
                ),
            ),
            expected_query_results=(
                (
                    "SELECT sql FROM duckdb_views() "
                    "WHERE schema_name = 'review' AND view_name = 'stg_payments'",
                    (
                        (
                            "CREATE VIEW review.stg_payments AS SELECT * FROM "
                            "(SELECT CAST(payment_id AS INTEGER) AS payment_id, "
                            "CAST(order_id AS INTEGER) AS order_id, "
                            "CAST(amount_cents AS INTEGER) AS amount_cents "
                            "FROM raw_prod.raw_payments);",
                        ),
                    ),
                ),
                ("SELECT DISTINCT region FROM review.stg_orders", (("amer",),)),
            ),
        ),
        ClonePreparationE2ETestCase(
            description="selected model missing in the origin warns beside a copied one",
            clone_arguments=(
                "--from",
                "prod",
                "--to",
                "dev",
                "--select",
                "orders_backlog",
                "fct_orders",
            ),
            expected_assets=(_ALL_DEV_ASSETS[2], _ALL_DEV_ASSETS[4]),
            expected_query_results=(("SELECT count(*) FROM dev.fct_orders", ((2,),)),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_origin_environment_when_cloning_then_items_and_relations_match_selection(
    test_case: ClonePreparationE2ETestCase, origin_project: Path, tmp_path: Path
) -> None:
    project_dir: Path = _project_copy(origin_project=origin_project, tmp_path=tmp_path)
    json_path: Path = tmp_path / "clone.json"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "clone",
            *test_case.clone_arguments,
            "--json-output",
            str(json_path),
        ),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assets: list[dict[str, object]] = json.loads(json_path.read_text(encoding="utf-8"))["assets"]
    assert (
        tuple(
            (
                asset["kind"],
                asset["name"],
                asset["action"],
                asset.get("origin_relation"),
                asset["target"],
            )
            for asset in assets
        )
        == test_case.expected_assets
    )
    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        rows = query_duckdb(db_path=project_dir / "clone.duckdb", sql=query)
        assert tuple(tuple(row) for row in rows) == expected_rows


@pytest.mark.parametrize(
    "test_case",
    (
        CloneTerminalProgressE2ETestCase(
            description="finished preparation leaves no spinner over the clone output",
            columns=120,
            expected_screen_fragments=(
                "✓ Warehouse connected  duckdb",
                "Prepared clone plan.",
                "sqb clone  origin=prod destination=dev  (2 resources)",
                "fct_orders",
                "orders_backlog",
                "Completed with warnings",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_terminal_when_cloning_then_preparation_spinner_stops_before_items(
    test_case: CloneTerminalProgressE2ETestCase, origin_project: Path, tmp_path: Path
) -> None:
    project_dir: Path = _project_copy(origin_project=origin_project, tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb_with_pty(
        command=(
            "clone",
            "--from",
            "prod",
            "--to",
            "dev",
            "--select",
            "fct_orders",
            "orders_backlog",
        ),
        project_dir=project_dir,
        columns=test_case.columns,
    )

    screen: tuple[str, ...] = render_terminal_screen(
        output=result.stdout, columns=test_case.columns
    )
    rendered: str = "\n".join(screen)
    assert result.returncode == 0, rendered
    assert not any(glyph in rendered for glyph in SPINNER_GLYPHS), rendered
    assert_fragments_in_order(rendered, test_case.expected_screen_fragments)
    after_preparation: str = result.stdout.split("Prepared clone plan.", maxsplit=1)[1]
    assert not any(glyph in after_preparation for glyph in SPINNER_GLYPHS), after_preparation


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
