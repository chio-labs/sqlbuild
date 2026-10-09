"""Seeded SQL-test projects and both planning paths for the native planning glue tests."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from itertools import chain, compress
from operator import attrgetter
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlTest
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.planner._helpers.sql_tests import native_planning
from sqlbuild.compiler.planner.models import (
    NativeSqlTestArtifact,
    NativeSqlTestPlan,
    PlanWarning,
)
from sqlbuild.compiler.planner.types import WarningSeverity


@dataclass(frozen=True)
class PlanningCallOutcome:
    """What one planning call returned, or the type and text of what it raised."""

    value: object
    raised: tuple[str, str] | None


_PROJECT_TOML: str = (
    'name = "orders_testing"\nadapter = "duckdb"\n\n[connection]\ndatabase = "orders.duckdb"\n'
)
_SOURCES: str = """sources:
  - name: raw_orders
    description: Orders feed.
    schema: main
    table: raw_orders
    columns:
      - name: order_id
        type: INTEGER
      - name: customer_id
        type: INTEGER
      - name: amount
        type: INTEGER
      - name: status
        type: VARCHAR
      - name: ordered_at
        type: TIMESTAMP
  - name: raw_customers
    description: Customers feed.
    schema: main
    table: raw_customers
    columns:
      - name: customer_id
        type: INTEGER
      - name: region
        type: VARCHAR
"""
_SEEDS: str = """seeds:
  - name: regions
    description: Region labels.
    columns:
      - name: region
        type: VARCHAR
      - name: label
        type: VARCHAR
"""
_MACROS: str = (
    "def cents(column: str) -> str:\n"
    '    return f"({column}) * 100"\n\n'
    "def known_region() -> str:\n"
    '    return "region IS NOT NULL"\n'
)
_UDF: str = (
    'FUNCTION (\n  description "Whether an amount is large",\n'
    "  arguments (amount INTEGER),\n  returns BOOLEAN,\n);\n\namount > 100\n"
)
_TABLE_FUNCTION: str = (
    'FUNCTION (\n  description "Orders of one customer",\n'
    "  arguments (p_customer_id INTEGER),\n"
    "  returns table (order_id INTEGER, amount INTEGER)\n);\n\n"
    'SELECT order_id, amount FROM __ref("stg_orders") WHERE customer_id = p_customer_id\n'
)
_BASE_MODELS: dict[str, str] = {
    "stg_orders": (
        'SELECT order_id, customer_id, amount, status, ordered_at\nFROM __source("raw_orders")'
    ),
    "stg_customers": (
        'SELECT customer_id, region\nFROM __source("raw_customers")\nWHERE @known_region()'
    ),
    "int_orders": (
        'SELECT o.order_id, o.customer_id, c.region, @cents("o.amount") AS amount_cents,\n'
        '  __udf("udf__is_big")(o.amount) AS is_big\n'
        'FROM __ref("stg_orders") o\nJOIN __ref("stg_customers") c ON o.customer_id = c.customer_id'
    ),
    "fct_regions": (
        "WITH totals AS (\n"
        '  SELECT region, SUM(amount_cents) AS total_cents FROM __ref("int_orders") GROUP BY 1\n'
        ")\nSELECT t.region, r.label, t.total_cents\n"
        'FROM totals t\nLEFT JOIN __seed("regions") r ON t.region = r.region'
    ),
    "customer_orders": ('SELECT order_id, amount\nFROM __table_fn("table_fn__customer_orders")(1)'),
}
_DAILY_ORDERS: str = (
    "MODEL (description 'Daily orders.',\n  materialized incremental,\n"
    "  incremental_strategy delete_insert,\n  cursor ordered_at,\n  cursor_type timestamp,\n"
    "  cursor_grain day,\n  cursor_inputs (raw_orders ordered_at,),\n);\n\n"
    "SELECT ordered_at, amount\n"
    'FROM __source("raw_orders")\n'
    "WHERE ordered_at >= __cursor_start() AND ordered_at < __cursor_end()\n"
)
_FIXTURES: dict[str, str] = {
    "__source__raw_orders": (
        "SELECT 1 AS order_id, 10 AS customer_id, 150 AS amount, 'placed' AS status, "
        "TIMESTAMP '2026-02-01 10:00:00' AS ordered_at"
    ),
    "__source__raw_customers": "SELECT 10 AS customer_id, 'east' AS region",
    "__seed__regions": "SELECT 'east' AS region, 'East' AS label",
    "__ref__stg_orders": (
        "SELECT 1 AS order_id, 10 AS customer_id, 150 AS amount, 'placed' AS status, "
        "TIMESTAMP '2026-02-01 10:00:00' AS ordered_at"
    ),
    "__ref__stg_customers": "SELECT 10 AS customer_id, 'east' AS region",
    "__ref__int_orders": (
        "SELECT 1 AS order_id, 10 AS customer_id, 'east' AS region, 15000 AS amount_cents, "
        "TRUE AS is_big"
    ),
    "__table_fn__table_fn__customer_orders": "SELECT 1 AS order_id, 150 AS amount",
    "__macro__cents": "SELECT 'amount'",
}
_UPSTREAM: dict[str, tuple[str, ...]] = {
    "stg_orders": ("__source__raw_orders",),
    "stg_customers": ("__source__raw_customers",),
    "int_orders": ("__ref__stg_orders", "__ref__stg_customers", "__source__raw_orders"),
    "fct_regions": ("__ref__int_orders", "__seed__regions", "__source__raw_customers"),
    "customer_orders": ("__table_fn__table_fn__customer_orders",),
    "daily_orders": ("__source__raw_orders",),
}
_DIRECT_TESTS: tuple[str, ...] = (
    'TEST (mode macro, name "doubles_cents");\n\nWITH\n'
    "amounts AS (SELECT 2 AS amount),\n"
    '__macro_actual__ AS (SELECT @cents("amount") AS cents FROM amounts),\n'
    "__macro_expected__ AS (SELECT 200 AS cents)\nSELECT 1\n",
    'TEST (mode udf, name "flags_big_amounts");\n\nWITH\n'
    '__udf_actual__ AS (SELECT __udf("udf__is_big")(150) AS is_big),\n'
    "__udf_expected__ AS (SELECT TRUE AS is_big)\nSELECT 1\n",
    'TEST (mode table_fn, name "lists_customer_orders");\n\nWITH\n'
    "__table_fn_actual__ AS (\n"
    '  SELECT order_id, amount FROM __table_fn("table_fn__customer_orders")(10)\n),\n'
    "__table_fn_expected__ AS (SELECT 1 AS order_id, 150 AS amount)\nSELECT 1\n",
)
_DIRECT_TEST_SHARE: float = 0.8
_STRAY_WINDOW_SHARE: float = 0.1
_MOCK_SHARE: float = 0.85
_MACRO_MOCK_SHARE: float = 0.5
_HELPER_SHARE: float = 0.4
_ASSERTION_SHARE: float = 0.2
_WINDOWS: tuple[str, ...] = (
    "",
    ', cursor_start "2026-02-01", cursor_end "2026-02-03"',
    ', cursor_start "2026-02-03", cursor_end "2026-02-01"',
)


def generated_sql_test_files(*, rng: random.Random, test_count: int) -> dict[str, str]:
    """A project of mocked, expected, asserted, helper, direct and failing SQL tests."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": _PROJECT_TOML,
        "sources/raw.yml": _SOURCES,
        "seeds/regions.yml": _SEEDS,
        "seeds/regions.csv": "region,label\neast,East\n",
        "macros/amounts.py": _MACROS,
        "functions/sql/udf__is_big.sql": _UDF,
        "functions/sql/table_fn__customer_orders.sql": _TABLE_FUNCTION,
        "models/daily_orders.sql": _DAILY_ORDERS,
    }
    files.update(
        (f"models/{name}.sql", f'MODEL (description "Model {name}.");\n\n{sql}\n')
        for name, sql in _BASE_MODELS.items()
    )
    files.update(
        (f"tests/unit/test_generated_{index}.sql", _model_test(rng=rng, index=index))
        for index in range(test_count)
    )
    files.update(
        compress(
            (
                (f"tests/unit/test_direct_{index}.sql", sql)
                for index, sql in enumerate(_DIRECT_TESTS)
            ),
            [rng.random() < _DIRECT_TEST_SHARE for _ in _DIRECT_TESTS],
        )
    )
    return files


def _model_test(*, rng: random.Random, index: int) -> str:
    """One model test: the first target's first mock, then random mocks, helper and checks."""

    targets: list[str] = rng.sample(sorted(_UPSTREAM), k=rng.choice((1, 1, 2)))
    windowed: bool = "daily_orders" in targets or rng.random() < _STRAY_WINDOW_SHARE
    window: str = rng.choice(((_WINDOWS[0],), _WINDOWS)[windowed])
    fixtures: list[str] = list(chain.from_iterable(_UPSTREAM[target] for target in targets))
    mocks: list[str] = [
        fixtures[0],
        *compress(fixtures, [rng.random() < _MOCK_SHARE for _ in fixtures]),
        *rng.sample(sorted(_FIXTURES), k=rng.choice((0, 0, 0, 1))),
        *(("__macro__cents",) * ("int_orders" in targets and rng.random() < _MACRO_MOCK_SHARE)),
    ]
    has_helper: bool = rng.random() < _HELPER_SHARE
    helper: str = f"wanted_{index}"
    helper_ctes: list[tuple[str, str]] = [
        (
            helper,
            rng.choice(
                ("SELECT 1 AS order_id", f'SELECT order_id FROM __ref("{rng.choice(targets)}")')
            ),
        )
    ][: int(has_helper)]
    expected_sql: str = ("SELECT 1 AS order_id", f"SELECT order_id FROM {helper}")[has_helper]
    checks: list[tuple[str, str]] = [
        (
            (f"__expected__{target}", expected_sql),
            (f"__assert__{target}_has_rows", f'SELECT * FROM __ref("{target}") WHERE 1 = 0'),
        )[rng.random() < _ASSERTION_SHARE]
        for target in targets
    ]
    ctes: dict[str, str] = {
        **{mock: _FIXTURES[mock] for mock in mocks},
        **dict(helper_ctes),
        **dict(checks),
    }
    body: str = ",\n".join(f"{name} AS (\n  {sql}\n)" for name, sql in ctes.items())
    return f'TEST (name "generated_{index}"{window});\n\nWITH\n{body}\nSELECT 1\n'


def compiled_project(*, project_dir: Path, files: dict[str, str]) -> CompiledProject:
    """Write and compile a project, keeping any compile diagnostics on it."""

    for relative_path, contents in files.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
    return build_project_graph(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter=DuckDbAdapter(),
    ).project


def use_sql_test_glue(*, monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    """Route SQL-test planning through the native glue, or through the JSON request."""

    monkeypatch.setattr(
        native_planning,
        "native_stage_enabled",
        lambda stage: enabled and stage is NativeStage.SQL_TEST_GLUE,
    )


def planning_outcome(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    render_sql: bool,
) -> PlanningCallOutcome:
    """The plans `plan_sql_tests_natively` returns, or what it raises."""

    return _outcome(
        lambda: native_planning.plan_sql_tests_natively(
            project=project,
            tests=tests,
            adapter=adapter,
            sql_analysis_enabled=project.settings.sql_analysis,
            render_sql=render_sql,
            include_plan=not render_sql,
        )
    )


def artifact_outcome(
    *,
    project: CompiledProject,
    tests: tuple[CompiledSqlTest, ...],
    adapter: BaseAdapter,
    glue: bool,
) -> PlanningCallOutcome:
    """Rendered artifacts from the glue or from the JSON request, or what planning raises."""

    plan: Callable[..., tuple[NativeSqlTestArtifact, ...]] = (
        native_planning.plan_and_render_sql_test_artifacts,
        native_planning.plan_compiled_sql_test_artifacts,
    )[glue]
    return _outcome(
        lambda: plan(
            project=project,
            tests=tests,
            adapter=adapter,
            sql_analysis_enabled=project.settings.sql_analysis,
        )
    )


def chain_outcome(
    *, project: CompiledProject, tests: tuple[CompiledSqlTest, ...]
) -> PlanningCallOutcome:
    """Each test's model chain, or what chain resolution raises."""

    return _outcome(
        lambda: native_planning.resolve_sql_test_model_chains(project=project, tests=tests)
    )


def outcome_kind(outcome: object) -> str:
    """`raised`, `errors` when a plan reports an error, or `planned`."""

    called: PlanningCallOutcome = cast(PlanningCallOutcome, outcome)
    plans: tuple[NativeSqlTestPlan, ...] = cast(tuple[NativeSqlTestPlan, ...], called.value or ())
    warnings: chain[PlanWarning] = chain.from_iterable(map(attrgetter("warnings"), plans))
    has_errors: bool = any(warning.severity is WarningSeverity.ERROR for warning in warnings)
    return ("planned", "errors", "raised", "raised")[has_errors + 2 * (called.raised is not None)]


def _outcome(call: Callable[[], object]) -> PlanningCallOutcome:
    try:
        return PlanningCallOutcome(value=call(), raised=None)
    except Exception as error:  # noqa: BLE001 - both paths must raise the same error
        return PlanningCallOutcome(value=None, raised=(type(error).__name__, str(error)))
