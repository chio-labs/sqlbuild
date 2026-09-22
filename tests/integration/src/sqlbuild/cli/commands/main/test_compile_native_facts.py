"""Real CLI and DuckDB coverage for the experimental borrowed query graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import duckdb
import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    DerivedNativeCompileTestCase,
    NativeCompilerModeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        DerivedNativeCompileTestCase(
            description="CTE column aliases survive a derived-table star",
            query_sql=(
                "WITH typed(order_id) AS (SELECT CAST(1 AS BIGINT) AS original_id) "
                "SELECT * FROM (SELECT order_id FROM typed) AS nested_orders"
            ),
            expected_exit_code=0,
            expected_diagnostics=(),
            expected_rows=((1,),),
        ),
        DerivedNativeCompileTestCase(
            description="both named-union branches survive a derived table",
            query_sql=(
                "WITH combined AS (SELECT CAST(1 AS BIGINT) AS order_id "
                "UNION ALL BY NAME SELECT CAST(2 AS BIGINT) AS order_id) "
                "SELECT * FROM (SELECT order_id FROM combined) AS nested_orders ORDER BY order_id"
            ),
            expected_exit_code=0,
            expected_diagnostics=(),
            expected_rows=((1,), (2,)),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_derived_native_facts_when_compiling_then_contract_and_execution_agree(
    test_case: DerivedNativeCompileTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SQLBUILD_EXPERIMENT_FOLDED_COMPILER", "1")
    monkeypatch.setenv("SQLBUILD_EXPERIMENT_FOLDED_FACTS", "1")
    monkeypatch.setenv("SQLBUILD_EXPERIMENT_FOLDED_INFERENCE", "1")
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "orders.sql").write_text(
        "MODEL (contract enforced, columns (order_id (type BIGINT, nullable false)));\n"
        + test_case.query_sql
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    result: dict[str, object] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, object]] = cast(list[dict[str, object]], result["diagnostics"])

    assert exit_code == test_case.expected_exit_code
    assert tuple(item["code"] for item in diagnostics) == test_case.expected_diagnostics
    compiled_sql: str = (tmp_path / "target" / "compiled" / "models" / "orders.sql").read_text()
    with duckdb.connect() as connection:
        rows: tuple[tuple[int, ...], ...] = tuple(connection.execute(compiled_sql).fetchall())
    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    (
        NativeCompilerModeTestCase(description="default compiler", flags=(), expected_edge_count=5),
        NativeCompilerModeTestCase(
            description="borrowed native graph",
            flags=("FOLDED_COMPILER", "FOLDED_FACTS", "FOLDED_INFERENCE"),
            expected_edge_count=5,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_input_and_output_share_name_when_compiling_then_lineage_keeps_input_dependency(
    test_case: NativeCompilerModeTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for flag in ("FOLDED_COMPILER", "FOLDED_FACTS", "FOLDED_INFERENCE"):
        monkeypatch.delenv(f"SQLBUILD_EXPERIMENT_{flag}", raising=False)
    for flag in test_case.flags:
        monkeypatch.setenv(f"SQLBUILD_EXPERIMENT_{flag}", "1")
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    models: Path = tmp_path / "models"
    models.mkdir()
    sources: Path = tmp_path / "sources"
    sources.mkdir()
    (sources / "orders.yml").write_text(
        "sources:\n  - name: orders\n    contract: enforced\n"
        "    expression: orders_input\n    columns:\n"
        "      - name: order_id\n        type: INTEGER\n"
        "      - name: amount\n        type: DOUBLE\n"
        "      - name: status\n        type: VARCHAR\n"
    )
    (models / "order_totals.sql").write_text(
        "MODEL (contract enforced, columns (order_id (type INTEGER), "
        "status (type VARCHAR), total (type DOUBLE)));\n"
        "SELECT order_id, "
        "CAST(CASE WHEN order_id % 2 = 0 THEN 'even' ELSE 'odd' END AS VARCHAR) AS status, "
        "CAST(CASE WHEN order_id % 2 = 0 THEN amount + 2 "
        "WHEN status = 'priority' THEN amount * 2 ELSE amount - 1 END AS DOUBLE) AS total "
        'FROM __source("orders") AS input'
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    result: dict[str, object] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["diagnostics"] == []
    resources: dict[str, object] = cast(dict[str, object], result["resources"])
    compiled_models: list[dict[str, object]] = cast(list[dict[str, object]], resources["models"])
    lineage: dict[str, object] = cast(dict[str, object], compiled_models[0]["lineage"])
    # order_id and the status alias each depend on order_id; total depends on
    # order_id, amount, and the physical status column, for five edges in total.
    assert lineage["edge_count"] == test_case.expected_edge_count
    compiled_sql: str = (
        tmp_path / "target" / "compiled" / "models" / "order_totals.sql"
    ).read_text()
    with duckdb.connect() as connection:
        connection.execute(
            "CREATE TABLE orders_input AS SELECT 1 AS order_id, "
            "CAST(10 AS DOUBLE) AS amount, 'priority' AS status"
        )
        # Compiled artifacts retain logical source intrinsics. Bind this test's
        # single source to its physical table before executing the artifact.
        connection.execute("CREATE MACRO __source(name) AS TABLE SELECT * FROM orders_input")
        assert connection.execute(compiled_sql).fetchall() == [(1, "odd", 20.0)]
        connection.execute("UPDATE orders_input SET status = 'standard'")
        assert connection.execute(compiled_sql).fetchall() == [(1, "odd", 9.0)]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
