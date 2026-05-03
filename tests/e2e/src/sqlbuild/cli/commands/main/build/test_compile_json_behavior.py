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
            description="compile json preserves runtime-owned cursor placeholders",
            command=("compile", "--json"),
            expected_exit_code=0,
            expected_model_names=(
                "customer_status_snapshot",
                "hourly_order_activity",
                "daily_activity_rollup",
            ),
            expected_sql_fragments=("__SQB_CURSOR_START__", "__SQB_CURSOR_END__"),
        )
    ],
    ids=["compile json preserves runtime-owned cursor placeholders"],
)
def test_given_waffle_shop_when_running_compile_json_then_runtime_owned_models_keep_placeholders(
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
    models: list[dict[str, object]] = payload["models"]
    selected_models: list[dict[str, object]] = [
        model for model in models if str(model["name"]) in test_case.expected_model_names
    ]
    assert len(selected_models) == len(test_case.expected_model_names)
    fragment: str
    for fragment in test_case.expected_sql_fragments:
        assert any(
            fragment in str(model["resolved_sql"]) and fragment in str(model["logical_ddl"])
            for model in selected_models
        )
