"""Binding-mode models with identical SQL shapes and inputs share one native query."""

import json
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.compile.models import CompactBatchPreparation
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import SharedBindingQueryCase
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import (
    trace_native_compact_batches,
    write_shared_binding_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SharedBindingQueryCase(
            description="identical shapes and inputs share one query",
            orders_summary_sql='MODEL (materialized view); SELECT id, amount FROM __ref("orders")',
            customers_summary_sql='MODEL (materialized view); SELECT id, amount FROM __ref("customers")',
            expected_shared_queries=1,
        ),
        SharedBindingQueryCase(
            description="a relation name used as a qualifier is not shared",
            orders_summary_sql=(
                'MODEL (materialized view); SELECT orders.id FROM __ref("orders") AS orders'
            ),
            customers_summary_sql=(
                'MODEL (materialized view); SELECT customers.id FROM __ref("customers") AS customers'
            ),
            expected_shared_queries=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_models_with_equal_shapes_when_compiling_then_shares_only_lossless_queries(
    test_case: SharedBindingQueryCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_shared_binding_project(project_dir=tmp_path, test_case=test_case)
    preparations: list[CompactBatchPreparation] = trace_native_compact_batches(monkeypatch)

    assert main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"]) == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert payload["diagnostics"] == []
    assert (
        sum(len(preparation.shared_query_indexes) for preparation in preparations)
        == test_case.expected_shared_queries
    )
    for model, upstream in (("orders_summary", "orders"), ("customers_summary", "customers")):
        assert (
            main(
                [
                    "--project-dir",
                    str(tmp_path),
                    "lineage",
                    f"{model}.id",
                    "--format",
                    "json",
                    "--direction",
                    "upstream",
                ]
            )
            == 0
        )
        lineage: dict[str, Any] = json.loads(capsys.readouterr().out)
        assert [step["source"]["resource_name"] for step in lineage["trace"]] == [upstream]


@pytest.mark.parametrize(
    "test_case",
    [
        SharedBindingQueryCase(
            description="findings after the relation keep each model's names and positions",
            orders_summary_sql=(
                'MODEL (materialized view); SELECT id FROM __ref("orders") WHERE missing > 0'
            ),
            customers_summary_sql=(
                'MODEL (materialized view); SELECT id FROM __ref("customers") WHERE missing > 0'
            ),
            expected_shared_queries=1,
            expected_codes=("B002",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_shared_query_with_finding_when_compiling_then_reports_each_model_exactly(
    test_case: SharedBindingQueryCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_shared_binding_project(project_dir=tmp_path, test_case=test_case)
    preparations: list[CompactBatchPreparation] = trace_native_compact_batches(monkeypatch)

    assert main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"]) == 1
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert (
        sum(len(preparation.shared_query_indexes) for preparation in preparations)
        == test_case.expected_shared_queries
    )
    findings: dict[str, dict[str, Any]] = {
        diagnostic["resource_name"]: diagnostic for diagnostic in payload["diagnostics"]
    }
    assert sorted(findings) == ["customers_summary", "orders_summary"]
    for model, upstream, sql in (
        ("orders_summary", "orders", test_case.orders_summary_sql),
        ("customers_summary", "customers", test_case.customers_summary_sql),
    ):
        finding: dict[str, Any] = findings[model]
        assert (finding["code"],) == test_case.expected_codes
        assert finding["message"] == f"Unknown column 'missing' in {upstream}"
        assert finding["location"]["column"] == sql.index("missing") + 1
        assert finding["location"]["end_column"] == sql.index("missing") + len("missing") + 1


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
