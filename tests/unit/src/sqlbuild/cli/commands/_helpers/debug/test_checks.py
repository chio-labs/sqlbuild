"""Debug diagnostics for command-group warehouses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild._native import run_debug_command
from sqlbuild.cli.commands._helpers.runtime.warehouse_scope import command_warehouse_scope
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
    test_case: DebugWarehouseVarsTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.project_contents, encoding="utf-8")

    with command_warehouse_scope(command="debug", cli_warehouse=None, cli_vars=test_case.cli_vars):
        exit_code: int = run_debug_command(
            project_dir=tmp_path, no_connection=True, json_output=True
        )

    payload: dict[str, list[dict[str, str]]] = json.loads(capsys.readouterr().out)
    lines: list[dict[str, str]] = payload["configuration"] + payload["connection"]
    reported: set[tuple[str, str, str]] = {
        (line["label"], line["message"], line.get("status_message", "")) for line in lines
    }
    assert exit_code == 0
    assert set(test_case.expected_lines) <= reported


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
