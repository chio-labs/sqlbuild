"""Real CLI coverage for the warehouse each command group's Snowflake sessions select."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    CommandWarehouseCliTestCase,
    CommandWarehouseDebugJsonTestCase,
    CommandWarehouseExitTestCase,
    CommandWarehouseOutputTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    install_offline_snowflake_connector,
    write_snowflake_warehouse_project,
)

_RAW_QUERY_DIFF_ARGS: tuple[str, ...] = (
    "diff",
    "--left-query",
    "SELECT 1 AS order_id",
    "--right-query",
    "SELECT 1 AS order_id",
    "--key",
    "order_id",
)
_LOCAL_QUERY_OVERRIDE: str = '[targets.dev.warehouses]\nquery = "LOCAL_ADHOC_WH"\n'
_LOCAL_DUCKDB_OVERRIDE: str = (
    'adapter = "duckdb"\n\n'
    "[connections.local]\n"
    'database = "dev.duckdb"\n\n'
    "[targets.dev]\n"
    'connection = "local"\n'
    'database = "dev"\n'
)
_MISSING_ENV_QUERY_GROUP: str = (
    '[targets.dev.warehouses]\nbuild = "BUILD_WH"\nquery = "${ENV:SQB_EXAMPLE_MISSING_QWH}"\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        CommandWarehouseCliTestCase(
            description="build plans and executes on the build warehouse",
            argv=("build",),
            expected_warehouse="BUILD_WH",
        ),
        CommandWarehouseCliTestCase(
            description="plan inspects on the build warehouse",
            argv=("plan",),
            expected_warehouse="BUILD_WH",
        ),
        CommandWarehouseCliTestCase(
            description="query runs on the query warehouse",
            argv=("query", "SELECT 1"),
            expected_warehouse="ADHOC_WH",
        ),
        CommandWarehouseCliTestCase(
            description="raw query diff runs on the query warehouse",
            argv=_RAW_QUERY_DIFF_ARGS,
            expected_warehouse="ADHOC_WH",
        ),
        CommandWarehouseCliTestCase(
            description="cli warehouse overrides the build group",
            argv=("build", "--warehouse", "CLI_WH"),
            expected_warehouse="CLI_WH",
        ),
        CommandWarehouseCliTestCase(
            description="cli warehouse overrides the query group",
            argv=("query", "SELECT 1", "--warehouse", "CLI_WH"),
            expected_warehouse="CLI_WH",
        ),
        CommandWarehouseCliTestCase(
            description="local query group overrides the project query group",
            argv=("query", "SELECT 1"),
            local_config=_LOCAL_QUERY_OVERRIDE,
            expected_warehouse="LOCAL_ADHOC_WH",
        ),
        CommandWarehouseCliTestCase(
            description="local query group leaves the project build group",
            argv=("plan",),
            local_config=_LOCAL_QUERY_OVERRIDE,
            expected_warehouse="BUILD_WH",
        ),
        CommandWarehouseCliTestCase(
            description="quoted cli warehouse is passed through",
            argv=("query", "SELECT 1", "--warehouse", '"Adhoc WH"'),
            expected_warehouse='"Adhoc WH"',
        ),
        CommandWarehouseCliTestCase(
            description="missing env var in the query group does not affect build",
            argv=("build",),
            warehouses_section=_MISSING_ENV_QUERY_GROUP,
            expected_warehouse="BUILD_WH",
        ),
        CommandWarehouseCliTestCase(
            description="unset groups keep the connection warehouse for build",
            argv=("build",),
            warehouses_section="",
            expected_warehouse="ANALYTICS_WH",
        ),
        CommandWarehouseCliTestCase(
            description="unset groups keep the connection warehouse for diff",
            argv=_RAW_QUERY_DIFF_ARGS,
            warehouses_section="",
            expected_warehouse="ANALYTICS_WH",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_command_group_when_running_cli_then_every_session_uses_one_warehouse(
    test_case: CommandWarehouseCliTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_snowflake_warehouse_project(
        project_dir=tmp_path,
        warehouses_section=test_case.warehouses_section,
        local_config=test_case.local_config,
    )
    connect_calls, executed_sql = install_offline_snowflake_connector(monkeypatch)

    main(["--no-color", "--project-dir", str(tmp_path), *test_case.argv])

    capsys.readouterr()
    assert connect_calls
    assert {call.get("warehouse") for call in connect_calls} == {test_case.expected_warehouse}
    assert set(filter(lambda sql: sql.startswith("USE WAREHOUSE"), executed_sql)) == {
        f"USE WAREHOUSE {test_case.expected_warehouse}"
    }


@pytest.mark.parametrize(
    "test_case",
    [
        CommandWarehouseOutputTestCase(
            description="verbose build header names the warehouse and its source",
            argv=("build", "--verbose"),
            expected_fragments=(
                "warehouse    BUILD_WH (sqlbuild_project.toml [targets.dev.warehouses] build)",
            ),
        ),
        CommandWarehouseOutputTestCase(
            description="debug text reports each group and its fallback",
            argv=("debug", "--no-connection"),
            warehouses_section="",
            local_config='[targets.dev.warehouses]\nquery = "ADHOC_WH"\n',
            expected_fragments=(
                "build warehouse: ANALYTICS_WH [OK connection warehouse]",
                "query warehouse: ADHOC_WH [OK sqlbuild_local.toml [targets.dev.warehouses] query]",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warehouse_groups_when_running_cli_then_output_reports_warehouse_source(
    test_case: CommandWarehouseOutputTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_snowflake_warehouse_project(
        project_dir=tmp_path,
        warehouses_section=test_case.warehouses_section,
        local_config=test_case.local_config,
    )
    install_offline_snowflake_connector(monkeypatch)

    main(["--no-color", "--project-dir", str(tmp_path), *test_case.argv])

    output: str = capsys.readouterr().out
    assert all(fragment in output for fragment in test_case.expected_fragments)


@pytest.mark.parametrize(
    "test_case",
    [
        CommandWarehouseDebugJsonTestCase(
            description="configured groups report their target section",
            argv=("debug", "--json", "--no-connection"),
            expected_lines=(
                (
                    "build warehouse",
                    "BUILD_WH",
                    "sqlbuild_project.toml [targets.dev.warehouses] build",
                ),
                (
                    "query warehouse",
                    "ADHOC_WH",
                    "sqlbuild_project.toml [targets.dev.warehouses] query",
                ),
                ("warehouse", "ADHOC_WH", ""),
            ),
        ),
        CommandWarehouseDebugJsonTestCase(
            description="cli warehouse reports the flag for both groups",
            argv=("debug", "--json", "--no-connection", "--warehouse", "CLI_WH"),
            expected_lines=(
                ("build warehouse", "CLI_WH", "--warehouse"),
                ("query warehouse", "CLI_WH", "--warehouse"),
                ("warehouse", "CLI_WH", ""),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warehouse_groups_when_running_debug_json_then_each_group_reports_its_source(
    test_case: CommandWarehouseDebugJsonTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_snowflake_warehouse_project(
        project_dir=tmp_path,
        warehouses_section='[targets.dev.warehouses]\nbuild = "BUILD_WH"\nquery = "ADHOC_WH"\n',
        local_config="",
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), *test_case.argv])

    payload: dict[str, list[dict[str, str]]] = json.loads(capsys.readouterr().out)
    reported: set[tuple[str, str, str]] = {
        (line["label"], line["message"], line.get("status_message", ""))
        for line in (*payload["configuration"], *payload["connection"])
    }
    assert exit_code == 0
    assert set(test_case.expected_lines) <= reported


@pytest.mark.parametrize(
    "test_case",
    [
        CommandWarehouseExitTestCase(
            description="local duckdb override compiles with shared groups",
            argv=("compile",),
            local_config=_LOCAL_DUCKDB_OVERRIDE,
            expected_exit_code=0,
            expected_fragments=("Project compiled",),
        ),
        CommandWarehouseExitTestCase(
            description="local duckdb override builds with shared groups",
            argv=("build", "--verbose"),
            warehouses_section=_MISSING_ENV_QUERY_GROUP,
            local_config=_LOCAL_DUCKDB_OVERRIDE,
            expected_exit_code=0,
            expected_fragments=("warehouse    not set", "Completed successfully"),
        ),
        CommandWarehouseExitTestCase(
            description="local duckdb override reports shared groups as unused",
            argv=("debug", "--no-connection"),
            local_config=_LOCAL_DUCKDB_OVERRIDE,
            expected_exit_code=0,
            expected_fragments=(
                "build warehouse: not used (adapter duckdb)",
                "query warehouse: not used (adapter duckdb)",
            ),
        ),
        CommandWarehouseExitTestCase(
            description="local duckdb override rejects a cli warehouse before running",
            argv=("test", "--warehouse", "ADHOC_WH"),
            local_config=_LOCAL_DUCKDB_OVERRIDE,
            expected_exit_code=1,
            expected_fragments=(
                "error[C260]: --warehouse ADHOC_WH was given, but the 'duckdb' adapter",
            ),
        ),
        CommandWarehouseExitTestCase(
            description="blank cli warehouse is rejected before connecting",
            argv=("plan", "--warehouse", "  "),
            expected_exit_code=1,
            expected_fragments=("error[C261]: --warehouse requires a warehouse name",),
        ),
        CommandWarehouseExitTestCase(
            description="injected cli warehouse is rejected before connecting",
            argv=("query", "SELECT 1", "--warehouse", "x; drop table t"),
            expected_exit_code=1,
            expected_fragments=(
                "error[C261]: --warehouse 'x; drop table t' is not a valid Snowflake warehouse",
            ),
        ),
        CommandWarehouseExitTestCase(
            description="injected group warehouse is rejected before connecting",
            argv=("query", "SELECT 1"),
            warehouses_section='[targets.dev.warehouses]\nquery = "x; drop table t"\n',
            expected_exit_code=1,
            expected_fragments=(
                "error[C261]: sqlbuild_project.toml [targets.dev.warehouses] query resolves to "
                "'x; drop table t', which is not a valid Snowflake warehouse identifier",
                "[targets.dev.warehouses]",
                'query = "ADHOC_WH"',
            ),
        ),
        CommandWarehouseExitTestCase(
            description="debug reports a broken group and keeps checking",
            argv=("debug", "--no-connection"),
            warehouses_section=_MISSING_ENV_QUERY_GROUP,
            expected_exit_code=1,
            expected_fragments=(
                "build warehouse: BUILD_WH [OK sqlbuild_project.toml [targets.dev.warehouses] "
                "build]",
                "query warehouse: error: targets.dev.warehouses.query references missing ENV "
                "variable 'SQB_EXAMPLE_MISSING_QWH'",
                "connection test: [SKIP skipped by --no-connection]",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warehouse_inputs_when_running_cli_then_exit_and_output_match(
    test_case: CommandWarehouseExitTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("SQB_EXAMPLE_MISSING_QWH", raising=False)
    write_snowflake_warehouse_project(
        project_dir=tmp_path,
        warehouses_section=test_case.warehouses_section,
        local_config=test_case.local_config,
    )
    connect_calls, _ = install_offline_snowflake_connector(monkeypatch)

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), *test_case.argv])

    captured: CaptureResult[str] = capsys.readouterr()
    output: str = captured.out + captured.err
    assert exit_code == test_case.expected_exit_code
    assert all(fragment in output for fragment in test_case.expected_fragments)
    assert len(connect_calls) == test_case.expected_connect_calls


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
