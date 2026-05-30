"""Tests for Python-node result normalization and fan-in policies."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.python_nodes.types import (
    PythonNodeFanInAction,
    PythonNodeKind,
    PythonNodeStatus,
    SkipMode,
)
from sqlbuild.executor.python_nodes.helpers.results import (
    build_python_node_failure_result,
    evaluate_python_node_fan_in,
    normalize_python_node_return,
)
from sqlbuild.executor.python_nodes.models import (
    PythonNodeExecutionResult,
    PythonNodeFanInDecision,
    PythonNodeResult,
    PythonNodeSkipResult,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    PythonNodeFailureResultTestCase,
    PythonNodeFanInPolicyTestCase,
    PythonNodeReturnNormalizationErrorTestCase,
    PythonNodeReturnNormalizationTestCase,
)

RETURN_NORMALIZATION_TEST_CASES: list[PythonNodeReturnNormalizationTestCase] = [
    PythonNodeReturnNormalizationTestCase(
        description="normalizes plain return as successful payload",
        kind=PythonNodeKind.TASK,
        returned={"rows": 3},
        expected_status=PythonNodeStatus.SUCCESS,
        expected_payload={"rows": 3},
        expected_metadata={},
        expected_materialized=None,
        expected_skip_mode=None,
        expected_skip_reason=None,
    ),
    PythonNodeReturnNormalizationTestCase(
        description="normalizes none return as empty success",
        kind=PythonNodeKind.TASK,
        returned=None,
        expected_status=PythonNodeStatus.SUCCESS,
        expected_payload=None,
        expected_metadata={},
        expected_materialized=None,
        expected_skip_mode=None,
        expected_skip_reason=None,
    ),
    PythonNodeReturnNormalizationTestCase(
        description="normalizes explicit asset result with materialized flag",
        kind=PythonNodeKind.ASSET,
        returned=PythonNodeResult(
            payload={"uri": "s3://exports/customers.parquet"},
            metadata={"format": "parquet"},
            materialized=False,
        ),
        expected_status=PythonNodeStatus.SUCCESS,
        expected_payload={"uri": "s3://exports/customers.parquet"},
        expected_metadata={"format": "parquet"},
        expected_materialized=False,
        expected_skip_mode=None,
        expected_skip_reason=None,
    ),
    PythonNodeReturnNormalizationTestCase(
        description="normalizes downstream skip signal",
        kind=PythonNodeKind.TASK,
        returned=PythonNodeSkipResult(
            reason="No new source rows",
            mode=SkipMode.DOWNSTREAM,
            metadata={"cursor": "2026-05-30"},
        ),
        expected_status=PythonNodeStatus.SKIPPED,
        expected_payload=None,
        expected_metadata={"cursor": "2026-05-30"},
        expected_materialized=None,
        expected_skip_mode=SkipMode.DOWNSTREAM,
        expected_skip_reason="No new source rows",
    ),
]

FAN_IN_POLICY_TEST_CASES: list[PythonNodeFanInPolicyTestCase] = [
    PythonNodeFanInPolicyTestCase(
        description="runs when there are no upstream nodes",
        upstream_statuses=(),
        upstream_skip_modes=(),
        expected_action=PythonNodeFanInAction.RUN,
        expected_reason=None,
    ),
    PythonNodeFanInPolicyTestCase(
        description="blocks when any upstream failed",
        upstream_statuses=(PythonNodeStatus.SUCCESS, PythonNodeStatus.FAILED),
        upstream_skip_modes=(None, None),
        expected_action=PythonNodeFanInAction.BLOCK,
        expected_reason="Upstream Python node failed: upstream_1",
    ),
    PythonNodeFanInPolicyTestCase(
        description="skips when any upstream hard-skipped downstream",
        upstream_statuses=(PythonNodeStatus.SUCCESS, PythonNodeStatus.SKIPPED),
        upstream_skip_modes=(None, SkipMode.DOWNSTREAM),
        expected_action=PythonNodeFanInAction.SKIP,
        expected_reason="Upstream Python node skipped downstream: upstream_1",
    ),
    PythonNodeFanInPolicyTestCase(
        description="runs with successful sibling when another upstream soft-skipped",
        upstream_statuses=(PythonNodeStatus.SUCCESS, PythonNodeStatus.SKIPPED),
        upstream_skip_modes=(None, SkipMode.SELF),
        expected_action=PythonNodeFanInAction.RUN,
        expected_reason=None,
    ),
    PythonNodeFanInPolicyTestCase(
        description="skips when all upstream nodes soft-skipped",
        upstream_statuses=(PythonNodeStatus.SKIPPED, PythonNodeStatus.SKIPPED),
        upstream_skip_modes=(SkipMode.SELF, SkipMode.SELF),
        expected_action=PythonNodeFanInAction.SKIP,
        expected_reason="All upstream Python nodes were skipped",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RETURN_NORMALIZATION_TEST_CASES,
    ids=[case.description for case in RETURN_NORMALIZATION_TEST_CASES],
)
def test_given_python_node_return_when_normalizing_then_returns_execution_result(
    test_case: PythonNodeReturnNormalizationTestCase,
) -> None:
    result: PythonNodeExecutionResult = normalize_python_node_return(
        node_name="fetch_orders",
        kind=test_case.kind,
        returned=test_case.returned,
    )

    assert result.node_name == "fetch_orders"
    assert result.kind == test_case.kind
    assert result.status == test_case.expected_status
    assert result.payload == test_case.expected_payload
    assert result.metadata == test_case.expected_metadata
    assert result.materialized == test_case.expected_materialized
    assert result.skip_mode == test_case.expected_skip_mode
    assert result.skip_reason == test_case.expected_skip_reason


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeReturnNormalizationErrorTestCase(
            description="rejects materialized flag on task result",
            kind=PythonNodeKind.TASK,
            returned=PythonNodeResult(materialized=False),
            expected_error_fragment="Only asset Python nodes",
        )
    ],
    ids=["rejects materialized flag on task result"],
)
def test_given_non_asset_materialized_result_when_normalizing_then_raises(
    test_case: PythonNodeReturnNormalizationErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        normalize_python_node_return(
            node_name="fetch_orders",
            kind=test_case.kind,
            returned=test_case.returned,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeFailureResultTestCase(
            description="records failed status and error message",
            error=RuntimeError("API unavailable"),
            expected_status=PythonNodeStatus.FAILED,
            expected_error_message="API unavailable",
        )
    ],
    ids=["records failed status and error message"],
)
def test_given_python_node_exception_when_building_failure_result_then_records_message(
    test_case: PythonNodeFailureResultTestCase,
) -> None:
    result: PythonNodeExecutionResult = build_python_node_failure_result(
        node_name="fetch_orders",
        kind=PythonNodeKind.TASK,
        error=test_case.error,
    )

    assert result.status == test_case.expected_status
    assert result.error_message == test_case.expected_error_message


@pytest.mark.parametrize(
    "test_case",
    FAN_IN_POLICY_TEST_CASES,
    ids=[case.description for case in FAN_IN_POLICY_TEST_CASES],
)
def test_given_upstream_python_node_results_when_evaluating_fan_in_then_returns_decision(
    test_case: PythonNodeFanInPolicyTestCase,
) -> None:
    upstream_results: tuple[PythonNodeExecutionResult, ...] = tuple(
        PythonNodeExecutionResult(
            node_name=f"upstream_{index}",
            kind=PythonNodeKind.TASK,
            status=status,
            skip_mode=test_case.upstream_skip_modes[index],
        )
        for index, status in enumerate(test_case.upstream_statuses)
    )

    decision: PythonNodeFanInDecision = evaluate_python_node_fan_in(
        upstream_results=upstream_results,
    )

    assert decision.action == test_case.expected_action
    assert decision.reason == test_case.expected_reason
