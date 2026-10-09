"""Every engine reports a project's contract and promotion diagnostics identically."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    NativeContractParityTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    CompileReuseRun,
    copy_compile_project,
    prepare_compile_reuse_project,
    replace_project_text,
    report_without_engine,
    run_reuse_compile,
    stderr_without_durations,
    write_project_file,
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
        NativeContractParityTestCase(
            description="every_contract_family_under_immediate_promotion",
            project_files={
                "models/contracts/contract_orders.sql": _ENFORCED_ORDERS,
                "models/contracts/contract_totals.sql": _IMPLICIT_TOTALS,
                "models/contracts/contract_empty.sql": _EMPTY_CONTRACT,
                "models/contracts/contract_order_amounts.sql": _ORDER_AMOUNTS,
                "models/contracts/contract_category_pivot.sql": _CATEGORY_PIVOT,
            },
            promotion_mode="immediate",
            engines=("python", "native", "native-preview"),
            expected_exit_code=1,
            expected_codes=frozenset({"K001", "K002", "K004", "K005", "K006", "K011"}),
            expected_contract_deferrals=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_contract_failures_when_compiling_with_each_engine_then_reports_match_python(
    test_case: NativeContractParityTestCase, tmp_path: Path
) -> None:
    prepared_project: Path = tmp_path / "orders"
    prepare_compile_reuse_project(project_dir=prepared_project)
    for relative_path, contents in test_case.project_files.items():
        write_project_file(prepared_project, relative_path, contents)
    replace_project_text(
        prepared_project,
        "sqlbuild_project.toml",
        "[settings]",
        f'[settings]\ntable_promotion_mode = "{test_case.promotion_mode}"',
    )
    runs: list[CompileReuseRun] = [
        run_reuse_compile(
            project_dir=copy_compile_project(
                source=prepared_project, destination=tmp_path / engine
            ),
            env={ANALYSIS_RECORD_DIR_ENV_VAR: str(tmp_path / f"{engine}-records")},
            global_args=("--compiler-engine", engine),
        )
        for engine in test_case.engines
    ]

    assert {run.returncode for run in runs} == {test_case.expected_exit_code}
    assert {report_without_engine(run) for run in runs} == {report_without_engine(runs[0])}
    assert {stderr_without_durations(stderr=run.stderr) for run in runs} == {
        stderr_without_durations(stderr=runs[0].stderr)
    }
    assert all(f'"code": "{code}"' in runs[0].report for code in test_case.expected_codes)
    assert _contract_deferrals(tmp_path / "native-preview-records") == (
        test_case.expected_contract_deferrals
    )


def _contract_deferrals(directory: Path) -> int:
    return sum(
        json.loads(line)["site"].startswith("contracts/")
        for path in sorted(directory.glob("analysis-deferrals-*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
