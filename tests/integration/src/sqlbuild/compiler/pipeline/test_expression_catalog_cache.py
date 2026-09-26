"""Expression schemas are memoized only within their owning compiler catalog."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.compile._helpers.assembly import semantic_shapes
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import ExpressionMemoCase


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
        'MODEL (materialized view); SELECT id FROM __source("raw_orders")'
    )
    (tmp_path / "sources").mkdir()
    source: Path = tmp_path / "sources/orders.yml"
    source.write_text(
        f"sources:\n  - name: raw_orders\n    expression: {test_case.expression}\n  - name: raw_customers\n    expression: {test_case.expression}\n"
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


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
