"""Every engine reports contract types and failures alike; preview compares types natively."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    NativeTypeSystemTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    report_without_engine,
    type_system_engine_compile,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project

_PROJECT_TOML: str = (
    'name = "orders"\nadapter = "duckdb"\n\n[connection]\ndatabase = "warehouse.duckdb"\n'
)
_ORDERS_MODEL: str = """MODEL (
  description "Orders with contracted column types.",
  materialized table,
  contract enforced,
  columns (
    order_id (type INTEGER),
    amount (type numeric( 10 , 2 )),
    note (type TEXT),
  ),
);

SELECT CAST(1 AS INT) AS order_id, CAST(2.5 AS DECIMAL(10, 2)) AS amount, CAST('gift' AS VARCHAR) AS note
"""
_ORDER_TOTALS_MODEL: str = """MODEL (
  description "Order totals whose contract disagrees with the query.",
  materialized table,
  contract enforced,
  columns (
    order_id (type BIGINT),
    total (type DECIMAL(12, 2)),
  ),
);

SELECT order_id, amount AS total FROM __ref("orders")
"""
_IMMEDIATE_PROMOTION_TOML: str = (
    _PROJECT_TOML + '\n[settings]\ntable_promotion_mode = "immediate"\n'
)
_ENFORCED_ORDERS: str = """MODEL (
  description "Orders with an enforced contract",
  materialized table,
  contract enforced,
  columns (
    order_id (type VARCHAR),
    customer_id (type INTEGER, nullable false),
    shipped_at (type TIMESTAMP),
    amount (type DOUBLE),
  ),
);

SELECT CAST(1 AS INTEGER) AS order_id, CAST(NULL AS INTEGER) AS customer_id,
  CAST(2.5 AS DOUBLE) AS amount, 'placed' AS status
"""
_IMPLICIT_TOTALS: str = """MODEL (
  description "Totals with declared columns and no enforced contract",
  columns (
    total_amount (type DOUBLE),
    order_count (type BIGINT),
  ),
);

SELECT CAST(2.5 AS DOUBLE) AS total_amount
"""
_EMPTY_CONTRACT: str = """MODEL (
  description "An enforced contract without columns",
  materialized view,
  contract enforced,
);

SELECT 1 AS order_id
"""
_ORDER_AMOUNTS: str = """MODEL (
  description "Typed order amounts per category",
  materialized view,
  contract enforced,
  columns (
    customer_id (type INTEGER),
    category (type VARCHAR),
    amount (type "DECIMAL(12,2)"),
  ),
);

SELECT CAST(1 AS INTEGER) AS customer_id, CAST('books' AS VARCHAR) AS category,
  CAST(10.25 AS DECIMAL(12,2)) AS amount
"""
_CATEGORY_PIVOT: str = """MODEL (
  description "Order amounts pivoted per category",
  materialized view,
  columns (customer_id (type INTEGER)),
  dynamic_columns (
    category_amounts (
      pivot_column category,
      value_column amount,
      aggregate MAX,
      type VARCHAR
    )
  ),
);

PIVOT __ref("contract_order_amounts")
ON category
USING MAX(amount)
GROUP BY customer_id
"""


@pytest.mark.parametrize(
    "test_case",
    [
        NativeTypeSystemTestCase(
            description="matching spellings pass and a changed precision is reported",
            project_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/orders.sql": _ORDERS_MODEL,
                "models/order_totals.sql": _ORDER_TOTALS_MODEL,
            },
            expected_exit_code=1,
            expected_report_text="inferred as numeric(10,2) but declared type is DECIMAL(12,2)",
        ),
        NativeTypeSystemTestCase(
            description="every contract family fails alike under immediate promotion",
            project_files={
                "sqlbuild_project.toml": _IMMEDIATE_PROMOTION_TOML,
                "models/contract_orders.sql": _ENFORCED_ORDERS,
                "models/contract_totals.sql": _IMPLICIT_TOTALS,
                "models/contract_empty.sql": _EMPTY_CONTRACT,
                "models/contract_order_amounts.sql": _ORDER_AMOUNTS,
                "models/contract_category_pivot.sql": _CATEGORY_PIVOT,
            },
            expected_exit_code=1,
            expected_report_text="contract enforced requires staged table promotion",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_contract_types_when_compiling_with_each_engine_then_reports_match_python(
    test_case: NativeTypeSystemTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outcomes: dict[str, tuple[CompileReuseRun, list[bool]]] = {
        engine: type_system_engine_compile(
            project_dir=prepare_inline_project(
                tmp_path=tmp_path, project_name=engine, repo_files=test_case.project_files
            ),
            engine=engine,
            monkeypatch=monkeypatch,
            capsys=capsys,
        )
        for engine in ("python", "native", "native-preview")
    }
    python_run, python_answers = outcomes["python"]
    native_run, native_answers = outcomes["native"]
    preview_run, preview_answers = outcomes["native-preview"]

    assert (python_run.returncode, native_run.returncode, preview_run.returncode) == (
        (test_case.expected_exit_code,) * 3
    )
    assert test_case.expected_report_text in python_run.report
    assert report_without_engine(native_run) == report_without_engine(python_run)
    assert report_without_engine(preview_run) == report_without_engine(python_run)
    assert (native_run.compiled, preview_run.compiled) == (python_run.compiled,) * 2
    assert (python_answers, native_answers, any(preview_answers)) == ([], [], True)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
