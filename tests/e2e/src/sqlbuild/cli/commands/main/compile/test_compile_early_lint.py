"""E2E tests for the speculative SQL lint started during compilation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    EarlyLintCompileTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    compile_json_payload,
    diagnostic_location_keys,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project

_PROJECT_TOML: str = 'name = "commerce"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL005"]\n'
_ORDERS_SQL: str = 'MODEL (description "Orders");\nSELECT 1 AS order_id, 2 AS amount\n'


@pytest.mark.parametrize(
    "test_case",
    (
        EarlyLintCompileTestCase(
            description="graph error discards the speculative lint",
            order_totals_sql=(
                'MODEL (description "Order totals");\n'
                "WITH\n"
                "  unused_orders AS (SELECT 1 AS order_id),\n"
                '  totals AS (SELECT order_id, missing_column FROM __ref("orders"))\n'
                "SELECT order_id FROM totals\n"
            ),
            expected_exit_code=1,
            expected_diagnostics=(("B002", "models/order_totals.sql", 4, 31),),
        ),
        EarlyLintCompileTestCase(
            description="clean graph reports every lint finding at its authored line",
            order_totals_sql=(
                'MODEL (description "Order totals");\n'
                "WITH\n"
                "  unused_orders AS (SELECT 1 AS order_id),\n"
                '  totals AS (SELECT order_id, amount FROM __ref("orders")),\n'
                "\n"
                "  unused_amounts AS (\n"
                "    SELECT amount FROM totals\n"
                "  ),\n"
                "  unused_counts AS (SELECT COUNT(*) AS order_count FROM totals)\n"
                "SELECT order_id, amount FROM totals\n"
            ),
            expected_exit_code=1,
            expected_diagnostics=(
                ("SQBRSQL005", "models/order_totals.sql", 3, 3),
                ("SQBRSQL005", "models/order_totals.sql", 6, 3),
                ("SQBRSQL005", "models/order_totals.sql", 9, 3),
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_rules_enabled_project_when_compiling_cold_and_warm_then_lint_wait_is_attributed(
    test_case: EarlyLintCompileTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="commerce",
        repo_files={
            "sqlbuild_project.toml": _PROJECT_TOML,
            "models/orders.sql": _ORDERS_SQL,
            "models/order_totals.sql": test_case.order_totals_sql,
        },
    )

    cold_exit: int
    cold: dict[str, Any]
    cold_exit, cold = compile_json_payload(project_dir=project_dir)
    warm_exit: int
    warm: dict[str, Any]
    warm_exit, warm = compile_json_payload(project_dir=project_dir)

    assert (cold_exit, warm_exit) == (test_case.expected_exit_code, test_case.expected_exit_code)
    assert diagnostic_location_keys(cold) == test_case.expected_diagnostics
    assert diagnostic_location_keys(warm) == test_case.expected_diagnostics
    for payload in (cold, warm):
        wait_ms: object = payload["compile_timings"]["early_lint_wait_ms"]
        assert isinstance(wait_ms, int)
        assert wait_ms >= 0
