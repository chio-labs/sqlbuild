"""E2E tests for compile --json behavior."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    CompileJsonBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_waffle_shop, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        CompileJsonBuildE2ETestCase(
            description="compile json reports offline query sql",
            command=("compile", "--json"),
            expected_exit_code=0,
            expected_model_names=(
                "customer_status_snapshot",
                "hourly_order_activity",
                "daily_activity_rollup",
            ),
            expected_sql_fragments=('__ref("fact_orders")', "DATE_TRUNC"),
        )
    ],
    ids=["compile json reports offline query sql"],
)
def test_given_waffle_shop_when_running_compile_json_then_it_reports_offline_query_sql(
    test_case: CompileJsonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    payload: dict[str, object] = json.loads(result.stdout)
    assert payload["offline"] is True
    assert payload["command"] == "compile"
    assert payload["has_errors"] is False
    summary: dict[str, object] = payload["summary"]
    assert summary["models"] >= len(test_case.expected_model_names)
    assert summary["errors"] == 0
    assert summary["warnings"] == 0
    assert payload["diagnostics"] == []
    timings: dict[str, object] = payload["compile_timings"]
    assert "total_ms" in timings
    artifacts: dict[str, object] = payload["artifacts"]
    assert artifacts["compiled_sql_dir"] == "target/compiled/"
    assert artifacts["manifest"] is None
    resources: dict[str, object] = payload["resources"]
    models: list[dict[str, object]] = resources["models"]
    selected_models: list[dict[str, object]] = [
        model for model in models if str(model["name"]) in test_case.expected_model_names
    ]
    assert len(selected_models) == len(test_case.expected_model_names)
    fragment: str
    for fragment in test_case.expected_sql_fragments:
        assert any(fragment in str(model["query_sql"]) for model in selected_models)
    fact_orders: dict[str, object] = next(
        model for model in models if model["name"] == "fact_orders"
    )
    assert fact_orders["materialized"] == "table"
    assert fact_orders["column_count"] == 14
    assert fact_orders["lineage"] == {
        "available": True,
        "column_count": 14,
        "edge_count": 15,
        "has_star": False,
    }
    assert {dep["name"] for dep in fact_orders["depends_on"]} >= {
        "stg_orders",
        "stg_payments",
        "waffle_types",
    }
    assert resources["seeds"]
    assert resources["functions"]
    assert resources["audits"]
    assert resources["tests"]
    assert all("logical_ddl" not in model for model in models)
    assert all("action" not in model for model in models)
