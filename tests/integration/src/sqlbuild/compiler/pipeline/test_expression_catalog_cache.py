"""Expression schemas are memoized only within their owning compiler catalog."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.compile._helpers.assembly import semantic_shapes
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    ExpressionBatchCase,
    ExpressionMemoCase,
)


@pytest.mark.parametrize(
    "test_case",
    [ExpressionMemoCase("shared closed expression", "SELECT 1 AS id")],
    ids=lambda case: case.description,
)
def test_given_equal_source_expressions_when_compiling_then_infers_once_and_invalidates_changed_content(
    test_case: ExpressionMemoCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    (tmp_path / "models").mkdir()
    (tmp_path / "models/orders.sql").write_text(
        'MODEL (description "Test model orders.", materialized view); SELECT id FROM __source("raw_orders")'
    )
    (tmp_path / "sources").mkdir()
    source: Path = tmp_path / "sources/orders.yml"
    source.write_text(
        f"sources:\n  - name: raw_orders\n    description: Test source raw_orders.\n    expression: {test_case.expression}\n  - name: raw_customers\n    description: Test source raw_customers.\n    expression: {test_case.expression}\n"
    )
    original: Callable[..., Any] = semantic_shapes.analyze_queries_with_compact_polyglot_batch
    calls: list[object] = []

    def traced(**kwargs: Any) -> Any:
        calls.append(kwargs["query_sqls"])
        return original(**kwargs)

    monkeypatch.setattr(semantic_shapes, "analyze_queries_with_compact_polyglot_batch", traced)
    args: list[str] = ["--project-dir", str(tmp_path), "compile", "--json"]
    assert main(args) == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert payload["diagnostics"] == []
    assert len(calls) == test_case.expected_analysis_calls
    source.write_text(source.read_text().replace("AS id", "AS quantity"))
    assert main(args) == 1
    changed: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert [item["code"] for item in changed["diagnostics"]] == ["B002"]
    assert len(calls) == test_case.expected_analysis_calls * 2


@pytest.mark.parametrize(
    "test_case",
    [
        ExpressionBatchCase(
            description="distinct expressions share one native batch and later passes reuse it",
            orders_expression="SELECT 1 AS id",
            customers_expression="SELECT 2 AS customer_id",
            expected_batches=(("SELECT 1 AS id", "SELECT 2 AS customer_id"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_distinct_source_expressions_when_compiling_then_infers_them_in_one_batch(
    test_case: ExpressionBatchCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    (tmp_path / "models").mkdir()
    (tmp_path / "models/orders.sql").write_text(
        'MODEL (description "Test model orders.", materialized view); SELECT id FROM __source("raw_orders")'
    )
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources/orders.yml").write_text(
        "sources:\n"
        f"  - name: raw_orders\n    description: Test source raw_orders.\n    expression: {test_case.orders_expression}\n"
        f"  - name: raw_customers\n    description: Test source raw_customers.\n    expression: {test_case.customers_expression}\n"
    )
    original: Callable[..., Any] = semantic_shapes.analyze_queries_with_compact_polyglot_batch
    batches: list[tuple[str, ...]] = []

    def traced(**kwargs: Any) -> Any:
        batches.append(kwargs["query_sqls"])
        return original(**kwargs)

    monkeypatch.setattr(semantic_shapes, "analyze_queries_with_compact_polyglot_batch", traced)
    assert main(["--project-dir", str(tmp_path), "compile", "--json"]) == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert payload["diagnostics"] == []
    assert tuple(batches) == test_case.expected_batches


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
