"""Every engine compiles, inspects and runs SQL tests alike while the preview plans them natively."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_test_glue._test_types import (
    NativeSqlTestGlueCliTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.sql_test_glue.helpers import (
    EngineSqlTestRun,
    engine_sql_test_run,
)

_ENGINES: tuple[str, ...] = ("python", "native", "native-preview")
_ORDER_ROWS: str = (
    "SELECT 1 AS order_id, 10 AS customer_id, 150 AS amount, "
    "TIMESTAMP '2026-02-01 10:00:00' AS ordered_at\n"
    "  UNION ALL SELECT 2, 11, 20, TIMESTAMP '2026-02-05 09:00:00'"
)
_PROJECT: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders_testing"\nadapter = "duckdb"\n\n[connection]\ndatabase = "orders.duckdb"\n'
    ),
    "sources/raw.yml": (
        "sources:\n"
        "  - name: raw_orders\n    description: Orders feed.\n    expression: >-\n"
        "      (SELECT 1 AS order_id, 10 AS customer_id, 150 AS amount,\n"
        "      TIMESTAMP '2026-02-01 10:00:00' AS ordered_at)\n"
        "    columns:\n      - name: order_id\n        type: INTEGER\n"
        "      - name: customer_id\n        type: INTEGER\n"
        "      - name: amount\n        type: INTEGER\n"
        "      - name: ordered_at\n        type: TIMESTAMP\n"
        "  - name: raw_customers\n    description: Customers feed.\n    expression: >-\n"
        "      (SELECT 10 AS customer_id, 'east' AS region)\n"
        "    columns:\n      - name: customer_id\n        type: INTEGER\n"
        "      - name: region\n        type: VARCHAR\n"
    ),
    "macros/amounts.py": ('def cents(column: str) -> str:\n    return f"({column}) * 100"\n'),
    "models/staging/stg_orders.sql": (
        'MODEL (description "Staged orders");\n\n'
        'SELECT order_id, customer_id, amount, ordered_at FROM __source("raw_orders")\n'
    ),
    "models/staging/stg_customers.sql": (
        'MODEL (description "Staged customers");\n\n'
        'SELECT customer_id, region FROM __source("raw_customers") WHERE region IS NOT NULL\n'
    ),
    "models/marts/order_regions.sql": (
        'MODEL (description "Orders with regions");\n\n'
        'WITH big AS (\n  SELECT * FROM __ref("stg_orders") WHERE amount > 100\n)\n'
        'SELECT b.order_id, c.region, @cents("b.amount") AS amount_cents\n'
        'FROM big b JOIN __ref("stg_customers") c ON b.customer_id = c.customer_id\n'
    ),
    "models/marts/daily_orders.sql": (
        "MODEL (description 'Daily orders',\n  materialized incremental,\n"
        "  incremental_strategy delete_insert,\n  cursor ordered_at,\n  cursor_type timestamp,\n"
        "  cursor_grain day,\n  cursor_inputs (raw_orders ordered_at,),\n);\n\n"
        'SELECT ordered_at, amount\nFROM __source("raw_orders")\n'
        "WHERE ordered_at >= __cursor_start() AND ordered_at < __cursor_end()\n"
    ),
    "tests/unit/test_order_regions.sql": (
        'TEST (name "big_orders_get_regions");\n\nWITH\n'
        f"__source__raw_orders AS (\n  {_ORDER_ROWS}\n),\n"
        "__source__raw_customers AS (SELECT 10 AS customer_id, 'east' AS region),\n"
        "east AS (SELECT 'east' AS region),\n"
        "__expected__order_regions AS (\n"
        "  SELECT 1 AS order_id, region, 15000 AS amount_cents FROM east\n),\n"
        "__assert__amounts_are_positive AS (\n"
        '  SELECT * FROM __ref("order_regions") WHERE amount_cents <= 0\n)\n'
        "SELECT 1\n\n"
        'TEST (name "mocked_cents");\n\nWITH\n'
        "__macro__cents AS (SELECT 'amount'),\n"
        "__ref__stg_orders AS (\n"
        "  SELECT 1 AS order_id, 10 AS customer_id, 150 AS amount,\n"
        "  TIMESTAMP '2026-02-01' AS ordered_at\n),\n"
        "__ref__stg_customers AS (SELECT 10 AS customer_id, 'east' AS region),\n"
        "__expected__order_regions AS (\n"
        "  SELECT 1 AS order_id, 'east' AS region, 150 AS amount_cents\n)\n"
        "SELECT 1\n\n"
        'TEST (name "wrong_region");\n\nWITH\n'
        "__ref__stg_orders AS (\n"
        "  SELECT 1 AS order_id, 10 AS customer_id, 150 AS amount,\n"
        "  TIMESTAMP '2026-02-01' AS ordered_at\n),\n"
        "__ref__stg_customers AS (SELECT 10 AS customer_id, 'east' AS region),\n"
        "__expected__order_regions AS (\n"
        "  SELECT 1 AS order_id, 'west' AS region, 15000 AS amount_cents\n)\n"
        "SELECT 1\n"
    ),
    "tests/unit/test_daily_orders.sql": (
        'TEST (name "default_window");\n\nWITH\n'
        f"__source__raw_orders AS (\n  {_ORDER_ROWS}\n),\n"
        "__expected__daily_orders AS (\n"
        "  SELECT TIMESTAMP '2026-02-01 10:00:00' AS ordered_at, 150 AS amount\n"
        "  UNION ALL SELECT TIMESTAMP '2026-02-05 09:00:00' AS ordered_at, 20 AS amount\n)\n"
        "SELECT 1\n\n"
        'TEST (name "declared_window", cursor_start "2026-02-01", cursor_end "2026-02-03");\n\n'
        f"WITH\n__source__raw_orders AS (\n  {_ORDER_ROWS}\n),\n"
        "__expected__daily_orders AS (\n"
        "  SELECT TIMESTAMP '2026-02-01 10:00:00' AS ordered_at, 150 AS amount\n)\n"
        "SELECT 1\n"
    ),
    "tests/unit/test_cents.sql": (
        'TEST (mode macro, name "doubles_cents");\n\nWITH\n'
        "amounts AS (SELECT 2 AS amount),\n"
        '__macro_actual__ AS (SELECT @cents("amount") AS cents FROM amounts),\n'
        "__macro_expected__ AS (SELECT 200 AS cents)\nSELECT 1\n"
    ),
}
_MISSING_MOCK_TEST: str = (
    'TEST (name "regions_without_customers");\n\nWITH\n'
    f"__source__raw_orders AS (\n  {_ORDER_ROWS}\n),\n"
    "__expected__order_regions AS (\n"
    "  SELECT 1 AS order_id, 'east' AS region, 15000 AS amount_cents\n)\n"
    "SELECT 1\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeSqlTestGlueCliTestCase(
            description="mocks, helpers, assertions, macro mocks, cursor windows and macro tests",
            files=_PROJECT,
            expected_compile_returncode=0,
            expected_test_returncode=1,
            expected_fragments=(
                "real models: stg_customers, stg_orders, order_regions",
                "boundary: stg_orders is replaced by __ref__stg_orders",
                '"status": "fail"',
                '"status": "pass"',
            ),
        ),
        NativeSqlTestGlueCliTestCase(
            description="a test missing a source mock fails planning with the planner's error",
            files={**_PROJECT, "tests/unit/test_missing_mock.sql": _MISSING_MOCK_TEST},
            expected_compile_returncode=1,
            expected_test_returncode=1,
            expected_fragments=(
                "test 'regions_without_customers': model 'stg_customers' references "
                '__source(\\"raw_customers\\") which has no mock',
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_tests_when_compiling_inspecting_and_testing_then_every_engine_agrees(
    test_case: NativeSqlTestGlueCliTestCase, tmp_path: Path
) -> None:
    runs: dict[str, EngineSqlTestRun] = {
        engine: engine_sql_test_run(root=tmp_path, files=test_case.files, engine=engine)
        for engine in _ENGINES
    }
    python_run: EngineSqlTestRun = runs["python"]
    combined_output: str = (
        python_run.compile_report + python_run.inspect_output + python_run.test_results
    )

    assert (
        {engine: run == python_run for engine, run in runs.items()},
        python_run.compile_returncode,
        python_run.test_returncode,
        bool(python_run.compiled_tests) or python_run.compile_returncode != 0,
        tuple(fragment in combined_output for fragment in test_case.expected_fragments),
    ) == (
        dict.fromkeys(_ENGINES, True),
        test_case.expected_compile_returncode,
        test_case.expected_test_returncode,
        True,
        (True,) * len(test_case.expected_fragments),
    ), combined_output
