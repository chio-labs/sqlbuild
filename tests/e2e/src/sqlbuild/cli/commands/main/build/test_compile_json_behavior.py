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
    models: list[dict[str, object]] = payload["models"]
    selected_models: list[dict[str, object]] = [
        model for model in models if str(model["name"]) in test_case.expected_model_names
    ]
    assert len(selected_models) == len(test_case.expected_model_names)
    fragment: str
    for fragment in test_case.expected_sql_fragments:
        assert any(fragment in str(model["query_sql"]) for model in selected_models)
    assert all("logical_ddl" not in model for model in models)
    assert all("action" not in model for model in models)
