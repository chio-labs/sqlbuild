from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.integrations.dagster import SqlBuildCliResource
from sqlbuild.integrations.dagster._helpers.invocation import SqlBuildCliInvocation
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterCliFailureTestCase,
    DagsterCliInvocationTestCase,
    DagsterCliJsonStreamTestCase,
    DagsterCliSelectionTestCase,
    DagsterCliStreamTestCase,
)
from tests.unit.src.sqlbuild.integrations.dagster.helpers import (
    assert_json_output_file_behavior,
    assert_positional_selector_behavior,
    assert_select_file_selector_behavior,
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
