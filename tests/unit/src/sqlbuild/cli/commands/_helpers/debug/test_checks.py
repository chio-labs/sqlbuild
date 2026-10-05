"""Debug diagnostics for command-group warehouses."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.debug.checks import build_debug_result
from sqlbuild.cli.commands._helpers.runtime.warehouse_scope import command_warehouse_scope
from sqlbuild.cli.commands.models import DebugResult
from tests.unit.src.sqlbuild.cli.commands._helpers.debug._test_types import (
    DebugWarehouseVarsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DebugWarehouseVarsTestCase(
            description="cli vars expand the group exactly as the connection does",
            project_contents="""
name = "orders"
adapter = "snowflake"
default_target = "dev"

[connections.main]
account = "example-account"
warehouse = "ANALYTICS_WH"

[targets.dev]
connection = "main"
schema = "DEV"

[targets.dev.warehouses]
query = "${adhoc_wh}"
""".strip(),
            cli_vars={"adhoc_wh": "VAR_ADHOC_WH"},
            expected_lines=(
                (
                    "query warehouse",
                    "VAR_ADHOC_WH",
                    "sqlbuild_project.toml [targets.dev.warehouses] query",
                ),
                ("build warehouse", "ANALYTICS_WH", "connection warehouse"),
                ("warehouse", "VAR_ADHOC_WH", ""),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cli_vars_when_building_debug_result_then_groups_use_invocation_vars(
    test_case: DebugWarehouseVarsTestCase, tmp_path: Path
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.project_contents, encoding="utf-8")

    with command_warehouse_scope(command="debug", cli_warehouse=None, cli_vars=test_case.cli_vars):
        result: DebugResult = build_debug_result(project_dir=tmp_path, check_connection=False)

    reported: set[tuple[str, str, str]] = {
        (line.label, line.message, line.status_message or "") for line in result.lines
    }
    assert set(test_case.expected_lines) <= reported


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
