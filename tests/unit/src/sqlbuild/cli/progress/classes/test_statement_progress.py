from __future__ import annotations

import pytest

from tests.unit.src.sqlbuild.cli.progress.classes._test_types import (
    StatementMonitorRaceCase,
    StatementProgressCase,
)
from tests.unit.src.sqlbuild.cli.progress.classes.helpers import (
    FakeFailingSlowAdapter,
    FakeSlowAdapter,
    FakeSlowAdapterWithoutQueryIdProvider,
    execute_statement_progress_case,
    run_monitor_capture_race,
)


@pytest.mark.parametrize(
    "test_case",
    (
        StatementProgressCase(
            description="snowflake completion includes announcement heartbeat and query ID",
            adapter="snowflake",
            query_id="01-query-orders",
            expected_context="model=orders  phase=create  kind=CREATE",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_slow_statement_when_it_completes_then_progress_is_announced_and_monitor_stops(
    test_case: StatementProgressCase,
) -> None:
    output, monitor_thread, error = execute_statement_progress_case(
        test_case=test_case, adapter_type=FakeSlowAdapter
    )

    assert f"statement  {test_case.expected_context}  START" in output
    assert f"statement  {test_case.expected_context}  RUNNING" in output
    assert f"query_id={test_case.query_id}" in output
    assert monitor_thread.is_alive() is False
    assert error is None


@pytest.mark.parametrize(
    "test_case",
    (
        StatementMonitorRaceCase(
            description="query ID capture racing with stop publishes once",
            query_id="01-query-race",
            expected_submission_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_query_id_capture_race_when_monitor_stops_then_submission_is_published_once(
    test_case: StatementMonitorRaceCase,
) -> None:
    submissions, provider_call_count, stopper_alive = run_monitor_capture_race(
        query_id=test_case.query_id
    )

    assert submissions == (test_case.query_id,)
    assert len(submissions) == test_case.expected_submission_count
    assert provider_call_count == 1
    assert stopper_alive is False


@pytest.mark.parametrize(
    "test_case",
    (
        StatementProgressCase(
            description="snowflake failure includes query ID",
            adapter="snowflake",
            query_id="01-query-failed",
            expected_context="model=orders  phase=create  kind=CREATE",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_slow_statement_when_it_fails_then_failure_has_query_id_and_monitor_stops(
    test_case: StatementProgressCase,
) -> None:
    output, monitor_thread, error = execute_statement_progress_case(
        test_case=test_case, adapter_type=FakeFailingSlowAdapter
    )

    assert f"statement  {test_case.expected_context}  FAIL" in output
    assert f"query_id={test_case.query_id}" in output
    assert monitor_thread.is_alive() is False
    assert str(error) == "warehouse statement failed"


@pytest.mark.parametrize(
    "test_case",
    (
        StatementProgressCase(
            description="duckdb progress omits query ID",
            adapter="duckdb",
            query_id=None,
            expected_context="model=orders  phase=create  kind=CREATE",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_adapter_without_query_ids_when_statement_runs_then_id_noise_is_omitted(
    test_case: StatementProgressCase,
) -> None:
    output, monitor_thread, error = execute_statement_progress_case(
        test_case=test_case, adapter_type=FakeSlowAdapterWithoutQueryIdProvider
    )

    assert f"statement  {test_case.expected_context}  START" in output
    assert f"statement  {test_case.expected_context}  RUNNING" in output
    assert "query_id=" not in output
    assert monitor_thread.is_alive() is False
    assert error is None
