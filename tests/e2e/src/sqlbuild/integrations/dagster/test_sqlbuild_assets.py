"""E2E tests for executing SQLBuild through Dagster assets."""

import os
import runpy
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import dagster as dg
import pytest
from dagster import (
    AssetCheckExecutionContext,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetKey,
    ExecuteInProcessResult,
    materialize,
)

from sqlbuild.cli.commands.main.playground import run_playground
from sqlbuild.integrations.dagster import (
    SqlBuildCliResource,
    SqlBuildProject,
    sqlbuild_assets,
    sqlbuild_scenario_checks,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    REPO_ROOT,
    prepare_source_loader_strategies,
    prepare_waffle_shop,
    table_exists,
)
from tests.e2e.src.sqlbuild.integrations.dagster._test_types import (
    DagsterPlaygroundE2ETestCase,
    DagsterSqlBuildE2ETestCase,
    DagsterSqlBuildFailedCheckE2ETestCase,
    DagsterSqlBuildLoaderE2ETestCase,
    DagsterSqlBuildScenarioE2ETestCase,
    DagsterSqlBuildSelectionE2ETestCase,
    DagsterSqlBuildStreamingE2ETestCase,
)
from tests.e2e.src.sqlbuild.integrations.dagster.helpers import (
    add_failing_daily_revenue_audits,
    check_names_for_asset,
    check_severity_for_asset,
    failed_check_severities_for_asset,
    materialization_metadata_keys,
    wait_for_captured_stdout_fragment,
    write_sqb_capture_command,
    write_sqb_streaming_command,
)

SELECTION_TEST_CASES: list[DagsterSqlBuildSelectionE2ETestCase] = [
    DagsterSqlBuildSelectionE2ETestCase(
        description="dagster subset selection runs sqlbuild with select file",
        selected_asset_keys=(("main", "waffle_types"),),
        expected_success=True,
        expected_selector_file_contents="waffle_types\n",
        expected_selector_log_line="waffle_types",
        expected_table_names=("waffle_types",),
    ),
    DagsterSqlBuildSelectionE2ETestCase(
        description="dagster multi-asset selection writes all sqlbuild selectors",
        selected_asset_keys=(
            ("raw_customers",),
            ("raw_orders",),
            ("raw_payments",),
            ("main", "waffle_types"),
            ("main", "stg_customers"),
            ("main", "stg_orders"),
            ("main", "stg_payments"),
        ),
        expected_success=True,
        expected_selector_file_contents=(
            "raw_payments\nwaffle_types\nstg_payments\nraw_customers\n"
            "raw_orders\nstg_customers\nstg_orders\n"
        ),
        expected_selector_log_line=(
            "raw_payments waffle_types stg_payments raw_customers "
            "raw_orders stg_customers stg_orders"
        ),
        expected_table_names=(
            "raw_customers",
            "raw_orders",
            "waffle_types",
            "stg_customers",
            "stg_orders",
            "stg_payments",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterSqlBuildE2ETestCase(
            description="dagster loads generated dag artifact and executes sqlbuild build",
            expected_success=True,
            expected_dag_artifact="target/sqlbuild_dag.json",
            expected_table_names=(
                "raw_customers",
                "raw_orders",
                "fact_orders",
                "dim_customers",
                "waffle_types",
            ),
            expected_asset_keys=(
                ("load__waffle_customers",),
                ("load__waffle_orders",),
                ("raw_customers",),
                ("raw_orders",),
                ("main", "waffle_types"),
                ("main", "is_completed_order"),
                ("main", "fact_orders"),
            ),
            expected_json_metadata_asset_key=("main", "fact_orders"),
            expected_json_metadata_keys=("duration_ms", "kind", "name", "status", "target"),
            expected_check_asset_key=("main", "fact_orders"),
            expected_check_names=("audit__not_null__order_id", "sql_test__test_fact_orders"),
            expected_warn_check_name="audit__not_null__order_id",
        )
    ],
    ids=["dagster loads generated dag artifact and executes sqlbuild build"],
)
def test_given_waffle_shop_when_executing_sqlbuild_assets_then_dagster_run_succeeds(
    test_case: DagsterSqlBuildE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    sqb_executable: Path = REPO_ROOT / ".venv" / "bin" / "sqb"
    sqlbuild_project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=(str(sqb_executable),),
    )
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")

    sqlbuild_project.prepare_if_dev()

    @sqlbuild_assets(project=sqlbuild_project, required_resource_keys={"sqb"})
    def sqlbuild_waffle_shop(context: AssetExecutionContext) -> Iterator[object]:
        yield from context.resources.sqb.cli(["build"], context=context).stream()

    result: ExecuteInProcessResult = materialize(
        [sqlbuild_waffle_shop],
        resources={"sqb": SqlBuildCliResource(project_dir=sqlbuild_project)},
    )

    assert result.success is test_case.expected_success
    assert sqlbuild_project.dag_path == project_dir / test_case.expected_dag_artifact
    assert sqlbuild_project.dag_path.exists()
    for table_name in test_case.expected_table_names:
        assert table_exists(db_path=project_dir / "waffle_shop.duckdb", table_name=table_name)
    assert set(test_case.expected_asset_keys) <= {
        tuple(asset_key.path) for asset_key in sqlbuild_waffle_shop.keys
    }
    assert set(test_case.expected_json_metadata_keys) <= materialization_metadata_keys(
        result=result,
        asset_key=test_case.expected_json_metadata_asset_key,
    )
    assert set(test_case.expected_check_names) <= check_names_for_asset(
        result=result,
        asset_key=test_case.expected_check_asset_key,
    )
    assert (
        check_severity_for_asset(
            result=result,
            asset_key=test_case.expected_check_asset_key,
            check_name=test_case.expected_warn_check_name,
        )
        == AssetCheckSeverity.WARN
    )
    rendered_logs: str = capsys.readouterr().err
    assert '"version": 1' not in rendered_logs
    assert '"assets": [' not in rendered_logs
    assert '"checks": [' not in rendered_logs


@pytest.mark.parametrize(
    "test_case",
    SELECTION_TEST_CASES,
    ids=[case.description for case in SELECTION_TEST_CASES],
)
def test_given_dagster_asset_selection_when_executing_sqlbuild_then_uses_select_file(
    test_case: DagsterSqlBuildSelectionE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    command_log_path: Path = tmp_path / "sqb_command_log.txt"
    selector_log_path: Path = tmp_path / "sqb_selector_log.txt"
    sqb_command: tuple[str, ...] = write_sqb_capture_command(
        root=tmp_path,
        command_log_path=command_log_path,
        selector_log_path=selector_log_path,
    )
    sqlbuild_project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=sqb_command,
    )
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")
    sqlbuild_project.prepare_if_dev()

    @sqlbuild_assets(project=sqlbuild_project, required_resource_keys={"sqb"})
    def sqlbuild_waffle_shop(context: AssetExecutionContext) -> Iterator[object]:
        yield from context.resources.sqb.cli(["build"], context=context).stream()

    result: ExecuteInProcessResult = materialize(
        [sqlbuild_waffle_shop],
        resources={"sqb": SqlBuildCliResource(project_dir=sqlbuild_project)},
        selection=[AssetKey(list(asset_key)) for asset_key in test_case.selected_asset_keys],
    )

    assert result.success is test_case.expected_success
    assert "build --select-file" in command_log_path.read_text(encoding="utf-8")
    assert selector_log_path.read_text(encoding="utf-8") == (
        test_case.expected_selector_file_contents
    )
    rendered_logs: str = capsys.readouterr().err
    assert "SQLBuild command:" in rendered_logs
    assert "build --select-file" in rendered_logs
    assert "SQLBuild selector file:" in rendered_logs
    assert f"SQLBuild selected assets from Dagster ({len(test_case.selected_asset_keys)}):" in (
        rendered_logs
    )
    assert test_case.expected_selector_log_line in rendered_logs
    for table_name in test_case.expected_table_names:
        assert table_exists(db_path=project_dir / "waffle_shop.duckdb", table_name=table_name)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterSqlBuildLoaderE2ETestCase(
            description="dagster selected loader asset runs sqlbuild load",
            selected_asset_key=("countries",),
            expected_success=True,
            expected_selector_file_contents="countries\n",
            expected_table_names=("raw_countries",),
            expected_metadata_asset_key=("countries",),
            expected_metadata_keys=(
                "duration_ms",
                "kind",
                "loader",
                "name",
                "rows_loaded",
                "status",
            ),
        )
    ],
    ids=["dagster selected loader asset runs sqlbuild load"],
)
def test_given_source_loader_project_when_executing_sqlbuild_load_asset_then_loader_runs(
    test_case: DagsterSqlBuildLoaderE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_source_loader_strategies(tmp_path=tmp_path)
    command_log_path: Path = tmp_path / "sqb_command_log.txt"
    selector_log_path: Path = tmp_path / "sqb_selector_log.txt"
    sqb_command: tuple[str, ...] = write_sqb_capture_command(
        root=tmp_path,
        command_log_path=command_log_path,
        selector_log_path=selector_log_path,
    )
    sqlbuild_project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=sqb_command,
    )
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")
    sqlbuild_project.prepare_if_dev()

    @sqlbuild_assets(project=sqlbuild_project, required_resource_keys={"sqb"})
    def sqlbuild_loaders(context: AssetExecutionContext) -> Iterator[object]:
        yield from context.resources.sqb.cli(["load"], context=context).stream()

    result: ExecuteInProcessResult = materialize(
        [sqlbuild_loaders],
        resources={"sqb": SqlBuildCliResource(project_dir=sqlbuild_project)},
        selection=[AssetKey(list(test_case.selected_asset_key))],
    )

    assert result.success is test_case.expected_success
    assert "load --select-file" in command_log_path.read_text(encoding="utf-8")
    assert selector_log_path.read_text(encoding="utf-8") == (
        test_case.expected_selector_file_contents
    )
    for table_name in test_case.expected_table_names:
        assert table_exists(
            db_path=project_dir / "source_loader_strategies.duckdb",
            table_name=table_name,
        )
    assert set(test_case.expected_metadata_keys) <= materialization_metadata_keys(
        result=result,
        asset_key=test_case.expected_metadata_asset_key,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterPlaygroundE2ETestCase(
            description="generated dagster playground materializes loader-backed waffle shop",
            expected_success=True,
            expected_table_names=("raw__customers", "raw__orders", "fact_orders"),
            expected_schema="dev",
        )
    ],
    ids=["generated dagster playground materializes loader-backed waffle shop"],
)
def test_given_generated_dagster_playground_when_materializing_assets_then_build_succeeds(
    test_case: DagsterPlaygroundE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playground_name: str = "dagster_waffle_shop"
    assert run_playground(tmp_path, playground_name, template="dagster") == 0
    project_dir: Path = tmp_path / playground_name
    sqb_bin_dir: Path = REPO_ROOT / ".venv" / "bin"
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")
    monkeypatch.setenv("PATH", f"{sqb_bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    generated_defs: dict[str, object] = runpy.run_path(
        str(project_dir / "dagster" / "definitions.py")
    )
    waffle_shop_assets: object = generated_defs["waffle_shop_assets"]
    sqlbuild_project: SqlBuildProject = generated_defs["SQLBUILD_PROJECT"]  # type: ignore[assignment]

    result: ExecuteInProcessResult = materialize(
        [waffle_shop_assets],
        resources={"sqb": SqlBuildCliResource(project_dir=sqlbuild_project)},
    )

    assert result.success is test_case.expected_success
    for table_name in test_case.expected_table_names:
        assert table_exists(
            db_path=project_dir / "waffle_shop_control.duckdb",
            table_name=table_name,
            schema=test_case.expected_schema,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterSqlBuildStreamingE2ETestCase(
            description="sqlbuild stdout is visible before process exits",
            selected_asset_key=("main", "waffle_types"),
            expected_stdout_fragment="streamed before exit\n",
        )
    ],
    ids=["sqlbuild stdout is visible before process exits"],
)
def test_given_sqlbuild_process_is_still_running_when_emitting_stdout_then_dagster_streams_output(
    test_case: DagsterSqlBuildStreamingE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    sqb_executable: Path = REPO_ROOT / ".venv" / "bin" / "sqb"
    sqlbuild_project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=(str(sqb_executable),),
    )
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")
    sqlbuild_project.prepare_if_dev()
    started_path: Path = tmp_path / "stream-started.txt"
    release_path: Path = tmp_path / "stream-release.txt"
    json_payload: str = (
        '{"version": 1, "command": "build", "status": "success", '
        '"summary": {}, "assets": [{"kind": "seed", "name": "waffle_types", '
        '"status": "success", "duration_ms": 1}], "checks": []}'
    )
    streaming_command: tuple[str, ...] = write_sqb_streaming_command(
        root=tmp_path,
        started_path=started_path,
        release_path=release_path,
        stdout_text=test_case.expected_stdout_fragment,
        json_payload=json_payload,
    )

    @sqlbuild_assets(project=sqlbuild_project, required_resource_keys={"sqb"})
    def sqlbuild_waffle_shop(context: AssetExecutionContext) -> Iterator[object]:
        yield from context.resources.sqb.cli(["build"], context=context).stream()

    result_out: list[ExecuteInProcessResult] = []
    error_out: list[BaseException] = []

    def run_materialize() -> None:
        try:
            result_out.append(
                materialize(
                    [sqlbuild_waffle_shop],
                    resources={
                        "sqb": SqlBuildCliResource(
                            project_dir=sqlbuild_project,
                            sqb_command=list(streaming_command),
                        )
                    },
                    selection=[AssetKey(list(test_case.selected_asset_key))],
                )
            )
        except BaseException as error:
            error_out.append(error)

    thread: threading.Thread = threading.Thread(target=run_materialize)
    thread.start()
    try:
        deadline: float = time.monotonic() + 10.0
        while not started_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert started_path.exists()
        rendered_stdout: str = wait_for_captured_stdout_fragment(
            capsys=capsys,
            expected_fragment=test_case.expected_stdout_fragment,
            deadline=deadline,
        )
        assert test_case.expected_stdout_fragment in rendered_stdout
    finally:
        release_path.write_text("release", encoding="utf-8")
        thread.join(timeout=10.0)

    assert not thread.is_alive()
    assert error_out == []
    assert result_out[0].success


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterSqlBuildFailedCheckE2ETestCase(
            description="failed warn and error audits stay linked to selected asset",
            selected_asset_key=("main", "daily_revenue"),
            expected_check_names=(
                "audit__forced_warning_failure__daily_revenue",
                "audit__forced_error_failure__daily_revenue",
            ),
        )
    ],
    ids=["failed warn and error audits stay linked to selected asset"],
)
def test_given_failing_sqlbuild_audits_when_executing_dagster_then_links_checks_with_severity(
    test_case: DagsterSqlBuildFailedCheckE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    sqb_executable: Path = REPO_ROOT / ".venv" / "bin" / "sqb"
    sqlbuild_project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=(str(sqb_executable),),
    )
    build_resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=project_dir,
        sqb_command=[str(sqb_executable)],
    )
    build_resource.cli(["build"]).wait()
    add_failing_daily_revenue_audits(project_dir=project_dir)
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")
    sqlbuild_project.prepare_if_dev()

    @sqlbuild_assets(project=sqlbuild_project, required_resource_keys={"sqb"})
    def sqlbuild_waffle_shop(context: AssetExecutionContext) -> Iterator[object]:
        yield from context.resources.sqb.cli(
            ["audit", "--select", "daily_revenue"],
            context=context,
            raise_on_error=False,
        ).stream()

    result: ExecuteInProcessResult = materialize(
        [sqlbuild_waffle_shop],
        resources={"sqb": SqlBuildCliResource(project_dir=sqlbuild_project)},
        selection=[AssetKey(list(test_case.selected_asset_key))],
    )

    assert result.success
    severities: dict[str, AssetCheckSeverity] = failed_check_severities_for_asset(
        result=result,
        asset_key=test_case.selected_asset_key,
    )
    assert set(test_case.expected_check_names) <= set(severities)
    assert severities["audit__forced_warning_failure__daily_revenue"] == AssetCheckSeverity.WARN
    assert severities["audit__forced_error_failure__daily_revenue"] == AssetCheckSeverity.ERROR


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterSqlBuildScenarioE2ETestCase(
            description="scenario test only runs scenarios attached to selected assets",
            selected_asset_keys=(("main", "daily_revenue"),),
            expected_command_fragment=(
                "scenario test daily_revenue_minimal daily_revenue_multi_order --json"
            ),
            unexpected_command_fragment="fact_order_retained_artifacts",
            daily_revenue_asset_key=("main", "daily_revenue"),
            expected_daily_revenue_check_names=(
                "scenario__daily_revenue_minimal",
                "scenario__daily_revenue_multi_order",
            ),
            scenario_order_prices_asset_key=("main", "scenario_order_prices"),
            unexpected_scenario_order_prices_check_names=(
                "scenario__fact_order_retained_artifacts",
            ),
        )
    ],
    ids=["scenario test only runs scenarios attached to selected assets"],
)
def test_given_sqlbuild_scenarios_when_executing_dagster_then_emits_scenario_checks(
    test_case: DagsterSqlBuildScenarioE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    sqb_executable: Path = REPO_ROOT / ".venv" / "bin" / "sqb"
    sqlbuild_project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=(str(sqb_executable),),
    )
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")
    sqlbuild_project.prepare_if_dev()

    @sqlbuild_assets(project=sqlbuild_project, required_resource_keys={"sqb"})
    def sqlbuild_waffle_shop(context: AssetExecutionContext) -> Iterator[object]:
        yield from context.resources.sqb.cli(["scenario", "test"], context=context).stream()

    result: ExecuteInProcessResult = materialize(
        [sqlbuild_waffle_shop],
        resources={"sqb": SqlBuildCliResource(project_dir=sqlbuild_project)},
        selection=[AssetKey(list(asset_key)) for asset_key in test_case.selected_asset_keys],
    )

    assert result.success
    rendered_logs: str = capsys.readouterr().err
    assert test_case.expected_command_fragment in rendered_logs
    assert test_case.unexpected_command_fragment not in rendered_logs
    assert set(test_case.expected_daily_revenue_check_names) <= check_names_for_asset(
        result=result,
        asset_key=test_case.daily_revenue_asset_key,
    )
    assert not set(test_case.unexpected_scenario_order_prices_check_names).intersection(
        check_names_for_asset(
            result=result,
            asset_key=test_case.scenario_order_prices_asset_key,
        )
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterSqlBuildScenarioE2ETestCase(
            description="scenario helper only runs selected scenario checks",
            selected_asset_keys=(("main", "daily_revenue"),),
            expected_command_fragment="scenario test daily_revenue_minimal --json",
            unexpected_command_fragment="daily_revenue_multi_order",
            daily_revenue_asset_key=("main", "daily_revenue"),
            expected_daily_revenue_check_names=("scenario__daily_revenue_minimal",),
            scenario_order_prices_asset_key=("main", "scenario_order_prices"),
            unexpected_scenario_order_prices_check_names=(
                "scenario__fact_order_retained_artifacts",
            ),
        )
    ],
    ids=["scenario helper only runs selected scenario checks"],
)
def test_given_scenario_check_selection_when_executing_dagster_then_runs_only_selected_scenarios(
    test_case: DagsterSqlBuildScenarioE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    sqb_executable: Path = REPO_ROOT / ".venv" / "bin" / "sqb"
    sqlbuild_project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=(str(sqb_executable),),
    )
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")
    sqlbuild_project.prepare_if_dev()

    @sqlbuild_scenario_checks(project=sqlbuild_project, required_resource_keys={"sqb"})
    def sqlbuild_waffle_shop_scenarios(context: AssetCheckExecutionContext) -> Iterator[object]:
        yield from context.resources.sqb.cli(["scenario", "test"], context=context).stream()

    result: ExecuteInProcessResult = materialize(
        [sqlbuild_waffle_shop_scenarios],
        resources={"sqb": SqlBuildCliResource(project_dir=sqlbuild_project)},
        selection=dg.AssetSelection.checks(
            dg.AssetCheckKey(
                asset_key=AssetKey(list(test_case.daily_revenue_asset_key)),
                name="scenario__daily_revenue_minimal",
            )
        ),
    )

    assert result.success
    rendered_logs: str = capsys.readouterr().err
    assert test_case.expected_command_fragment in rendered_logs
    assert test_case.unexpected_command_fragment not in rendered_logs
    assert set(test_case.expected_daily_revenue_check_names) <= check_names_for_asset(
        result=result,
        asset_key=test_case.daily_revenue_asset_key,
    )
    assert not set(test_case.unexpected_scenario_order_prices_check_names).intersection(
        check_names_for_asset(
            result=result,
            asset_key=test_case.scenario_order_prices_asset_key,
        )
    )
