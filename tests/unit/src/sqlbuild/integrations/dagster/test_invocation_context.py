"""Dagster-to-generic invocation-context translation tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sqlbuild.integrations.dagster._helpers.invocation_context import (
    dagster_invocation_context,
)
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterInvocationContextTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterInvocationContextTestCase(
            description="safe orchestration identifiers",
            expected_context={
                "integration": {
                    "name": "dagster",
                    "run_id": "dagster-run-1",
                    "job_name": "betfair_prices_job",
                    "step_key": "all_sqlbuild_assets",
                    "retry_number": 2,
                    "partition_key": "2026-09-06",
                }
            },
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dagster_context_when_translating_then_only_safe_identifiers_are_exposed(
    test_case: DagsterInvocationContextTestCase,
) -> None:
    context: SimpleNamespace = SimpleNamespace(
        run_id="dagster-run-1",
        job_name="betfair_prices_job",
        op_handle=SimpleNamespace(to_string=lambda: "all_sqlbuild_assets"),
        retry_number=2,
        has_partition_key=True,
        partition_key="2026-09-06",
        run_config={"password": "must-not-cross-boundary"},
        tags={"credential": "must-not-cross-boundary"},
    )

    assert dagster_invocation_context(context) == test_case.expected_context


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterInvocationContextTestCase(
            description="oversized identifier is omitted",
            expected_context={"integration": {"name": "dagster", "retry_number": 0}},
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_oversized_dagster_identifier_when_translating_then_capture_context_remains_bounded(
    test_case: DagsterInvocationContextTestCase,
) -> None:
    context: SimpleNamespace = SimpleNamespace(
        run_id="x" * 1_025,
        step_key="y" * 1_025,
        retry_number=0,
        has_partition_key=False,
    )

    assert dagster_invocation_context(context) == test_case.expected_context


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
