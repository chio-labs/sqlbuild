from __future__ import annotations

from collections import defaultdict
from collections.abc import Generator, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Any, cast
from unittest.mock import Mock

import pytest

from sqlbuild.integrations.dagster import SqlBuildCliResource
from sqlbuild.integrations.dagster.classes.sqlbuild_cli_invocation import SqlBuildCliInvocation
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterCliCloneFailureTestCase,
    DagsterCliCloneStreamTestCase,
    DagsterCliFailureTestCase,
    DagsterCliInvocationTestCase,
    DagsterCliJsonStreamTestCase,
    DagsterCliLiveCloneEventTestCase,
    DagsterCliLiveLogTestCase,
    DagsterCliSelectionTestCase,
    DagsterCliStreamTestCase,
)
from tests.unit.src.sqlbuild.integrations.dagster.helpers import (
    assert_json_output_file_behavior,
    assert_positional_selector_behavior,
    assert_select_file_selector_behavior,
    write_blocking_execution_event_command,
    write_blocking_fake_sqb_command,
    write_dagster_test_dag,
    write_fake_sqb_command,
)

dg: Any = pytest.importorskip("dagster")


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliInvocationTestCase(
            description="wait captures successful command output",
            command_stdout="built ok\n",
            command_stderr="warning line\n",
            command_exit_code=0,
            expected_success=True,
            expected_stdout="built ok\n",
            expected_stderr="warning line\n",
        ),
        DagsterCliInvocationTestCase(
            description="wait captures failing command output without raising when disabled",
            command_stdout="",
            command_stderr="boom\n",
            command_exit_code=7,
            expected_success=False,
            expected_stdout="",
            expected_stderr="boom\n",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_cli_resource_when_waiting_invocation_then_captures_process_result(
    test_case: DagsterCliInvocationTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            stderr=test_case.command_stderr,
            exit_code=test_case.command_exit_code,
        ),
    )

    invocation: SqlBuildCliInvocation = resource.cli(["build"], raise_on_error=False).wait()

    assert invocation.is_successful() is test_case.expected_success
    assert invocation.stdout == test_case.expected_stdout
    assert invocation.stderr == test_case.expected_stderr


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliLiveLogTestCase(
            description="unflushed subprocess output reaches Dagster before process completion",
            expected_stdout_lines=("started without explicit flush", "completed"),
            expected_stderr_lines=("warning without explicit flush",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_running_sqlbuild_command_when_output_arrives_then_dagster_logs_it_immediately(
    test_case: DagsterCliLiveLogTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    release_path: Path = tmp_path / "release"
    first_log_received: Event = Event()
    logger: Mock = Mock()
    logger.info.side_effect = lambda *_args: first_log_received.set()
    context: Any = type("LoggingContext", (), {"log": logger})()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_blocking_fake_sqb_command(
            root=tmp_path,
            release_path=release_path,
        ),
    )
    invocation: SqlBuildCliInvocation = resource.cli(
        ["build"], context=context, raise_on_error=False
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        wait_future: Future[SqlBuildCliInvocation] = executor.submit(invocation.wait)
        assert first_log_received.wait(timeout=3)
        assert not wait_future.done()
        release_path.write_text("continue", encoding="utf-8")
        completed_invocation: SqlBuildCliInvocation = wait_future.result(timeout=3)

    for line in test_case.expected_stdout_lines:
        logger.info.assert_any_call("SQLBuild: %s", line)
    for line in test_case.expected_stderr_lines:
        logger.warning.assert_any_call("SQLBuild: %s", line)
    assert completed_invocation.stdout == "".join(
        f"{line}\n" for line in test_case.expected_stdout_lines
    )
    assert completed_invocation.stderr == "".join(
        f"{line}\n" for line in test_case.expected_stderr_lines
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterCliLiveLogTestCase(
            description="verbose SQL stays in compute stdout instead of Dagster event logs",
            expected_stdout_lines=("    SELECT * FROM orders",),
            expected_stderr_lines=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_verbose_command_when_streaming_output_then_keeps_sql_out_of_context_log(
    test_case: DagsterCliLiveLogTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    logger: Mock = Mock()
    invocation: SqlBuildCliInvocation = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout="".join(f"{line}\n" for line in test_case.expected_stdout_lines),
        ),
    ).cli(
        ["build", "--verbose"],
        context=type("VerboseContext", (), {"log": logger})(),
        raise_on_error=False,
    )

    invocation.wait()

    assert invocation.stdout == "".join(f"{line}\n" for line in test_case.expected_stdout_lines)
    assert not any(
        call.args and call.args[0] == "SQLBuild: %s" for call in logger.info.call_args_list
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliStreamTestCase(
            description="stream yields materialize results for dag assets",
            command_stdout="built ok\n",
            command_exit_code=0,
            expected_asset_keys=(
                ("shared_order_feed",),
                ("analytics", "waffle_types"),
                ("analytics", "normalize_email"),
                ("analytics", "customers"),
                ("raw_orders_loader",),
                ("raw", "orders"),
                ("analytics", "orders"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_cli_resource_with_dag_when_streaming_then_yields_asset_results(
    test_case: DagsterCliStreamTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            exit_code=test_case.command_exit_code,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    results: list[Any] = list(resource.cli(args=["build"]).stream())

    assert (
        tuple(tuple(result.asset_key.path) for result in results) == test_case.expected_asset_keys
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliJsonStreamTestCase(
            description="stream yields execution json asset and check results",
            command_stdout=(
                '{"version": 1, "command": "build", "status": "success", '
                '"summary": {}, '
                '"assets": [{"kind": "model", "name": "orders", '
                '"status": "success", "duration_ms": 12}], '
                '"checks": [{"kind": "audit", "name": "not_null", '
                '"check_id": "audit:not_null:model:orders:order_id", '
                '"passed": true, "status": "pass", "severity": "warn", '
                '"row_count": 0}]}'
            ),
            selected_asset_keys=(("analytics", "orders"),),
            expected_asset_keys=(("analytics", "orders"),),
            expected_check_names=("audit__not_null__order_id",),
            expected_check_severities=("WARN",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_execution_json_when_streaming_then_yields_structured_dagster_events(
    test_case: DagsterCliJsonStreamTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type(
        "SelectedAssetContext",
        (),
        {
            "selected_asset_keys": {
                dg.AssetKey(list(asset_key)) for asset_key in test_case.selected_asset_keys
            }
        },
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=test_case.command_stdout),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    results: list[Any] = list(resource.cli(args=["build"], context=context).stream())

    materialize_results_by_status: defaultdict[bool, list[Any]] = defaultdict(list)
    check_results_by_status: defaultdict[bool, list[Any]] = defaultdict(list)
    for result in results:
        materialize_results_by_status[isinstance(result, dg.MaterializeResult)].append(result)
        check_results_by_status[isinstance(result, dg.AssetCheckResult)].append(result)
    materialize_results: list[Any] = materialize_results_by_status[True]
    check_results: list[Any] = check_results_by_status[True]
    assert tuple(tuple(result.asset_key.path) for result in materialize_results) == (
        test_case.expected_asset_keys
    )
    assert tuple(result.check_name for result in check_results) == test_case.expected_check_names
    assert tuple(result.severity.value for result in check_results) == (
        test_case.expected_check_severities
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliCloneStreamTestCase(
            description="clone execution yields materializations for successful items only",
            command_stdout=(
                '{"version": 1, "command": "clone", "status": "success", '
                '"summary": {"success_count": 2}, '
                '"assets": [{"kind": "model", "name": "orders", '
                '"status": "success", "action": "cloned"}, '
                '{"kind": "seed", "name": "waffle_types", '
                '"status": "success", "action": "copied"}], "checks": []}'
            ),
            expected_asset_keys=(("analytics", "waffle_types"), ("analytics", "orders")),
            expected_actions=("copied", "cloned"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_execution_json_when_streaming_then_yields_asset_materializations(
    test_case: DagsterCliCloneStreamTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type(
        "AggregateCloneContext",
        (),
        {"selected_asset_keys": {dg.AssetKey(["aggregate_clone"])}},
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=test_case.command_stdout),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    results: list[Any] = list(
        resource.cli(args=["clone", "--from", "prod"], context=context).stream()
    )

    assert all(isinstance(result, dg.AssetMaterialization) for result in results)
    assert (
        tuple(tuple(result.asset_key.path) for result in results) == test_case.expected_asset_keys
    )
    assert (
        tuple(result.metadata["action"].value for result in results) == test_case.expected_actions
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterCliLiveCloneEventTestCase(
            description="completed clone item materializes while subprocess remains blocked",
            command="clone",
            command_args=("clone", "--from", "prod"),
            expected_asset_key=("analytics", "orders"),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="completed build item materializes while subprocess remains blocked",
            command="build",
            command_args=("build",),
            expected_asset_key=("analytics", "orders"),
            expected_remaining_asset_keys=(("raw", "orders"),),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="partial JSONL writes are buffered until their record is complete",
            command="build",
            command_args=("build",),
            expected_asset_key=("analytics", "orders"),
            expected_remaining_asset_keys=(("raw", "orders"),),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="run uses the shared live execution event transport",
            command="run",
            command_args=("run",),
            expected_asset_key=("analytics", "orders"),
            expected_remaining_asset_keys=(("raw", "orders"),),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="test uses the shared live execution event transport",
            command="test",
            command_args=("test",),
            expected_asset_key=("analytics", "orders"),
            expected_remaining_asset_keys=(("raw", "orders"),),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="check uses the shared live execution event transport",
            command="check",
            command_args=("check",),
            expected_asset_key=("analytics", "orders"),
            expected_remaining_asset_keys=(("raw", "orders"),),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="audit uses the shared live execution event transport",
            command="audit",
            command_args=("audit",),
            expected_asset_key=("analytics", "orders"),
            expected_remaining_asset_keys=(("raw", "orders"),),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="seed uses the shared live execution event transport",
            command="seed",
            command_args=("seed",),
            expected_asset_key=("analytics", "orders"),
            expected_remaining_asset_keys=(("raw", "orders"),),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="load uses the shared live execution event transport",
            command="load",
            command_args=("load",),
            expected_asset_key=("analytics", "orders"),
            expected_remaining_asset_keys=(("raw", "orders"),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_running_clone_when_item_completes_then_materializes_before_process_exit(
    test_case: DagsterCliLiveCloneEventTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    release_path: Path = tmp_path / "release"
    context: Any = type("AggregateCloneContext", (), {"selected_asset_keys": set()})()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_blocking_execution_event_command(
            root=tmp_path,
            release_path=release_path,
            command=test_case.command,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )
    invocation: SqlBuildCliInvocation = resource.cli(args=test_case.command_args, context=context)
    stream: Iterator[Any] = invocation.stream()

    materialization: Any = next(stream)

    assert tuple(materialization.asset_key.path) == test_case.expected_asset_key
    assert invocation.process.poll() is None
    release_path.touch()
    remaining_results: list[Any] = list(stream)
    assert tuple(tuple(result.asset_key.path) for result in remaining_results) == (
        test_case.expected_remaining_asset_keys
    )
    assert invocation.returncode == 0


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterCliLiveCloneEventTestCase(
            description="closing a live event stream terminates its blocked subprocess",
            command="build",
            command_args=("build",),
            expected_asset_key=("analytics", "orders"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_blocked_command_when_live_stream_closes_then_subprocess_terminates(
    test_case: DagsterCliLiveCloneEventTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    invocation: SqlBuildCliInvocation = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_blocking_execution_event_command(
            root=tmp_path,
            release_path=tmp_path / "never-release",
            command=test_case.command,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    ).cli(
        args=test_case.command_args,
        context=type("LiveEventContext", (), {"selected_asset_keys": set()})(),
    )
    stream: Generator[Any, None, None] = cast(Generator[Any, None, None], invocation.stream())

    materialization: Any = next(stream)
    stream.close()

    assert tuple(materialization.asset_key.path) == test_case.expected_asset_key
    assert invocation.process.wait(timeout=3) is not None


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliCloneFailureTestCase(
            description="partial clone failure preserves confirmed materializations",
            command_stdout=(
                '{"version": 1, "command": "clone", "status": "failed", '
                '"summary": {"success_count": 1, "failure_count": 1}, '
                '"assets": [{"kind": "model", "name": "orders", '
                '"status": "success", "action": "cloned"}, '
                '{"kind": "model", "name": "customers", '
                '"status": "failed", "action": "failed"}], "checks": []}'
            ),
            expected_materialized_asset_key=("analytics", "orders"),
            expected_incomplete_assets="model:customers (failed)",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_clone_failure_when_streaming_then_preserves_confirmed_materializations(
    test_case: DagsterCliCloneFailureTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type("CloneContext", (), {"selected_asset_keys": set()})()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            exit_code=1,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )
    stream: Iterator[Any] = resource.cli(args=["clone", "--from", "prod"], context=context).stream()

    materialization: Any = next(stream)
    assert tuple(materialization.asset_key.path) == test_case.expected_materialized_asset_key
    with pytest.raises(dg.Failure) as exc_info:
        next(stream)

    incomplete_assets: Any = exc_info.value.metadata["incomplete_assets"]
    assert incomplete_assets.value == test_case.expected_incomplete_assets


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliFailureTestCase(
            description="clone failure without payload emits no materializations",
            command_stderr="clone crashed\n",
            command_exit_code=1,
            expected_error_fragment="SQLBuild CLI command failed with exit code 1",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_failure_without_payload_when_streaming_then_emits_no_materializations(
    test_case: DagsterCliFailureTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type("CloneContext", (), {"selected_asset_keys": set()})()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stderr=test_case.command_stderr,
            exit_code=test_case.command_exit_code,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    with pytest.raises(dg.Failure) as exc_info:
        next(resource.cli(args=["clone", "--from", "prod"], context=context).stream())

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliFailureTestCase(
            description="wait raises Dagster failure for nonzero command",
            command_stderr="build failed\n",
            command_exit_code=3,
            expected_error_fragment="SQLBuild CLI command failed with exit code 3",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_cli_resource_when_waiting_failed_invocation_then_raises_failure(
    test_case: DagsterCliFailureTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stderr=test_case.command_stderr,
            exit_code=test_case.command_exit_code,
        ),
    )

    with pytest.raises(dg.Failure) as error:
        resource.cli(args=["build"]).wait()

    assert test_case.expected_error_fragment in str(error.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliSelectionTestCase(
            description="selected Dagster asset appends SQLBuild selector",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("build",),
            expected_selectors=("orders",),
            assert_selector_transport=assert_select_file_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="explicit SQLBuild selector is preserved",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("build", "--select", "manual_selector"),
            expected_selectors=(),
            assert_selector_transport=assert_positional_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="selected Dagster asset appends attached scenario selectors",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("scenario", "test"),
            expected_selectors=("orders_minimal",),
            assert_selector_transport=assert_positional_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="explicit scenario selector is preserved",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("scenario", "test", "manual_scenario"),
            expected_selectors=(),
            assert_selector_transport=assert_positional_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="selected loader asset appends load selector",
            selected_asset_keys=(("shared_order_feed",),),
            command_args=("load",),
            expected_selectors=("shared_order_feed",),
            assert_selector_transport=assert_select_file_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="selected model asset is ignored for load selector",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("load",),
            expected_selectors=(),
            assert_selector_transport=assert_positional_selector_behavior,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selected_dagster_assets_when_invoking_cli_then_applies_sqlbuild_selectors(
    test_case: DagsterCliSelectionTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type(
        "SelectedAssetContext",
        (),
        {
            "selected_asset_keys": {
                dg.AssetKey(list(asset_key)) for asset_key in test_case.selected_asset_keys
            }
        },
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    invocation: SqlBuildCliInvocation = resource.cli(
        args=test_case.command_args,
        context=context,
    ).wait()

    assert invocation.is_successful()
    assert invocation.selection == test_case.expected_selectors
    test_case.assert_selector_transport(
        command=invocation.command,
        selectors=test_case.expected_selectors,
    )
    assert_json_output_file_behavior(command=invocation.command)
