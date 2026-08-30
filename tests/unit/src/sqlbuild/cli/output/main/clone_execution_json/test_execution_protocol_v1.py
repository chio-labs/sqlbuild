import json
from typing import Any

import pytest

from sqlbuild.cli.output.main._clone_execution_json import (
    format_clone_execution_json,
)
from sqlbuild.cli.output.main._clone_item_execution_event import (
    format_clone_item_execution_event,
)
from sqlbuild.cli.output.main._virtual_clone_execution_json import (
    format_virtual_clone_execution_json,
)
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.virtual.executor.models import VirtualCloneItemResult, VirtualCloneResult
from sqlbuild.virtual.state.types import PhysicalArtifactType
from tests.unit.src.sqlbuild.cli.output.main.clone_execution_json._test_types import (
    CloneExecutionJsonTestCase,
    CloneItemExecutionEventTestCase,
    VirtualCloneExecutionJsonTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneExecutionJsonTestCase(
            description="clone outcomes retain actions and tolerate missing origins",
            item_results=(
                CloneItemResult(
                    name="orders",
                    action=CloneAction.CLONED,
                    status=CloneStatus.SUCCESS,
                    origin_relation="prod.orders",
                    destination_relation="test.orders",
                    duration_seconds=0.012,
                ),
                CloneItemResult(
                    name="customers",
                    action=CloneAction.WARNING_MISSING_SOURCE,
                    status=CloneStatus.WARNING,
                    message="missing in origin environment",
                    origin_relation="prod.customers",
                    destination_relation="test.customers",
                ),
            ),
            expected_status="success",
            expected_asset_statuses=("success", "warning"),
            expected_asset_actions=("cloned", "warning_missing_source"),
            expected_summary={
                "success_count": 1,
                "failure_count": 0,
                "warning_count": 1,
                "total_count": 2,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_results_when_formatting_execution_json_then_preserves_asset_outcomes(
    test_case: CloneExecutionJsonTestCase,
) -> None:
    result: str = format_clone_execution_json(
        result=CloneExecutionResult(item_results=test_case.item_results),
        resource_types_by_name={"orders": "model", "customers": "model"},
    )

    payload: dict[str, Any] = json.loads(result)
    assets: list[dict[str, Any]] = payload["assets"]
    assert payload["version"] == 1
    assert payload["command"] == "clone"
    assert payload["status"] == test_case.expected_status
    assert tuple(asset["status"] for asset in assets) == test_case.expected_asset_statuses
    assert tuple(asset["action"] for asset in assets) == test_case.expected_asset_actions
    assert payload["summary"] == test_case.expected_summary


@pytest.mark.parametrize(
    "test_case",
    (
        CloneItemExecutionEventTestCase(
            description="completed clone item retains typed materialization metadata",
            item=CloneItemResult(
                name="orders",
                action=CloneAction.CLONED,
                status=CloneStatus.SUCCESS,
                origin_relation="prod.orders",
                destination_relation="test.orders",
                duration_seconds=0.012,
            ),
            resource_type="model",
            expected_asset={
                "kind": "model",
                "name": "orders",
                "status": "success",
                "action": "cloned",
                "duration_ms": 12,
                "origin_relation": "prod.orders",
                "target": "test.orders",
            },
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_completed_clone_item_when_formatting_event_then_emits_one_flushed_json_line(
    test_case: CloneItemExecutionEventTestCase,
) -> None:
    result: str = format_clone_item_execution_event(
        item=test_case.item,
        resource_type=test_case.resource_type,
    )

    payload: dict[str, Any] = json.loads(result)
    assert result.endswith("\n")
    assert payload["version"] == 1
    assert payload["command"] == "clone"
    assert payload["event"] == "asset"
    assert payload["asset"] == test_case.expected_asset


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCloneExecutionJsonTestCase(
            description="virtual clone reports reused and locked assets as completed",
            expected_status="success",
            expected_asset_statuses=("success", "skipped"),
            expected_summary={
                "success_count": 1,
                "failure_count": 0,
                "skipped_count": 1,
                "total_count": 2,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_clone_results_when_formatting_json_then_preserves_asset_outcomes(
    test_case: VirtualCloneExecutionJsonTestCase,
) -> None:
    result: str = format_virtual_clone_execution_json(
        result=VirtualCloneResult(
            mode="target",
            origin_environment="prod",
            destination_environment="test",
            item_results=(
                VirtualCloneItemResult(
                    artifact_type=PhysicalArtifactType.MODEL,
                    artifact_name="orders",
                    version_hash="abc",
                    action="reused",
                ),
                VirtualCloneItemResult(
                    artifact_type=PhysicalArtifactType.SEED,
                    artifact_name="countries",
                    version_hash="def",
                    action="skipped_locked",
                ),
            ),
        )
    )

    payload: dict[str, Any] = json.loads(result)
    assets: list[dict[str, Any]] = payload["assets"]
    assert payload["status"] == test_case.expected_status
    assert tuple(asset["status"] for asset in assets) == test_case.expected_asset_statuses
    assert payload["summary"] == test_case.expected_summary
