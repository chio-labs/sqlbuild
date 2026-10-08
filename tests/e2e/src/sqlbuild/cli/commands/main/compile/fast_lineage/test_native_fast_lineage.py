"""The preview engine builds fast column lineage natively with Python's exact CLI output."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile.fast_lineage._test_types import (
    NativeFastLineageCliTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.fast_lineage.helpers import (
    EngineLineageRun,
    engine_lineage_run,
    model_lineage_summaries,
)

_ENGINES: tuple[str, ...] = ("python", "native", "native-preview")
_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders_lineage"\nadapter = "duckdb"\n\n[connection]\ndatabase = "orders.duckdb"\n'
    ),
    "sources/raw.yml": (
        "sources:\n  - name: raw_orders\n    description: Orders feed.\n    expression: >-\n"
        "      (SELECT 1 AS order_id, 10 AS customer_id, CAST(5 AS DOUBLE) AS amount)\n"
        "    columns:\n      - name: order_id\n        type: INTEGER\n"
        "      - name: customer_id\n        type: INTEGER\n      - name: amount\n        type: DOUBLE\n"
    ),
    "models/staging/stg_orders.sql": (
        'MODEL (description "Staged orders");\n\nSELECT * FROM __source("raw_orders")\n'
    ),
    "models/marts/order_union.sql": (
        'MODEL (description "Orders twice", sql_analysis false);\n\n'
        'SELECT o.*, 1 AS copy_number FROM __ref("stg_orders") o\n'
        'UNION ALL\nSELECT *, 2 FROM __ref("stg_orders")\n'
    ),
    "models/marts/customer_totals.sql": (
        'MODEL (description "Totals per customer", sql_analysis false);\n\n'
        "WITH totals AS (\n"
        '  SELECT customer_id, SUM(amount) AS "Total_Amount" FROM __ref("order_union")\n'
        "  GROUP BY customer_id\n)\n"
        'SELECT T.customer_id, "Total_Amount", CAST("Total_Amount" AS BIGINT) AS rounded\n'
        "FROM totals AS T\n"
    ),
    "models/marts/order_copies.sql": (
        'MODEL (description "Order copies");\n\n'
        'SELECT u.*, c.rounded FROM __ref("order_union") u\n'
        'JOIN __ref("customer_totals") c ON u.customer_id = c.customer_id\n'
    ),
}

_DEEP_UNION_BRANCHES: int = 480
_DEEP_UNION_FILES: dict[str, str] = {
    "sqlbuild_project.toml": _PROJECT_FILES["sqlbuild_project.toml"],
    "sources/raw.yml": _PROJECT_FILES["sources/raw.yml"],
    "models/marts/orders_union.sql": (
        'MODEL (description "Orders repeated", sql_analysis false);\n\n'
        + " UNION ALL ".join(
            ['SELECT order_id, amount FROM __source("raw_orders")'] * _DEEP_UNION_BRANCHES
        )
        + "\n"
    ),
    "models/marts/orders_second.sql": (
        'MODEL (description "Order ids", sql_analysis false);\n\n'
        'SELECT order_id FROM __source("raw_orders")\n'
    ),
}


@pytest.mark.parametrize(
    "test_case",
    [
        NativeFastLineageCliTestCase(
            description="stars, opted-out unions, nested CTEs and quoted identifiers",
            files=_PROJECT_FILES,
            lineage_targets=(
                "customer_totals.Total_Amount",
                "order_union.amount",
                "stg_orders.amount",
            ),
            expected_lineage={
                "order_union": {
                    "available": True,
                    "column_count": 0,
                    "edge_count": 3,
                    "has_star": True,
                }
            },
            expected_minimum_python_fallback_parses=2,
            expected_minimum_traced_edges=4,
        ),
        NativeFastLineageCliTestCase(
            description="a 480-branch UNION ALL chain beside another opted-out model",
            files=_DEEP_UNION_FILES,
            lineage_targets=("orders_union.amount", "orders_second.order_id"),
            expected_lineage={
                "orders_union": {
                    "available": True,
                    "column_count": 0,
                    "edge_count": 2,
                    "has_star": False,
                },
                "orders_second": {
                    "available": True,
                    "column_count": 0,
                    "edge_count": 1,
                    "has_star": False,
                },
            },
            expected_minimum_python_fallback_parses=2,
            expected_minimum_traced_edges=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_compiling_with_each_engine_then_fast_lineage_output_matches(
    test_case: NativeFastLineageCliTestCase, tmp_path: Path
) -> None:
    runs: dict[str, EngineLineageRun] = {
        engine: engine_lineage_run(
            project_dir=tmp_path / engine,
            files=test_case.files,
            engine=engine,
            targets=test_case.lineage_targets,
        )
        for engine in _ENGINES
    }
    python: EngineLineageRun = runs["python"]
    summaries: dict[str, object] = model_lineage_summaries(python.compile_report)

    assert python.compile_returncode == 0, python.compile_report
    assert [code for code, _, _ in python.traces] == [0] * len(python.traces)
    assert {name: summaries[name] for name in test_case.expected_lineage} == (
        test_case.expected_lineage
    )
    assert sum('"source"' in stdout for _, stdout, _ in python.traces) >= (
        test_case.expected_minimum_traced_edges
    )
    assert python.fallback_parses >= test_case.expected_minimum_python_fallback_parses
    assert runs["native"] == python
    assert runs["native-preview"]._replace(fallback_parses=python.fallback_parses) == python
    assert runs["native-preview"].fallback_parses == 0


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
