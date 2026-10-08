"""Contracts compare type spellings through the native type system under the preview engine."""

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
    ],
    ids=lambda case: case.description,
)
def test_given_contract_types_when_compiling_with_preview_then_native_types_match_python(
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
        for engine in ("python", "native-preview")
    }
    python_run, python_answers = outcomes["python"]
    preview_run, preview_answers = outcomes["native-preview"]

    assert (python_run.returncode, preview_run.returncode) == (
        test_case.expected_exit_code,
        test_case.expected_exit_code,
    )
    assert test_case.expected_report_text in python_run.report
    assert report_without_engine(preview_run) == report_without_engine(python_run)
    assert preview_run.compiled == python_run.compiled
    assert (python_answers, any(preview_answers)) == ([], True)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
