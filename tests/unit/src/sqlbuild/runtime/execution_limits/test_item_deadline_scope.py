"""Per-item deadlines: expiry, watchdog cancellation and honest cancellation outcomes."""

from __future__ import annotations

import contextlib
import time

import pytest

from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.exceptions import ItemTimeoutError
from sqlbuild.runtime.execution_limits.main.current_execution_deadline import (
    current_execution_deadline,
)
from sqlbuild.runtime.execution_limits.main.enforce_execution_deadline import (
    enforce_execution_deadline,
)
from sqlbuild.runtime.execution_limits.main.execution_deadline_scope import (
    execution_deadline_scope,
)
from sqlbuild.runtime.execution_limits.main.execution_deadlines_suspended import (
    execution_deadlines_suspended,
)
from sqlbuild.runtime.execution_limits.main.item_deadline_scope import item_deadline_scope
from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy, ItemTimeoutReport
from sqlbuild.runtime.execution_limits.types import CancellationOutcome, ItemKind
from tests.unit.src.sqlbuild.runtime.execution_limits._test_types import (
    DeadlineCancellationTestCase,
    EarliestDeadlineTestCase,
    HeldClockTestCase,
    IdleExpiryTestCase,
    NestedDeadlineTestCase,
    NoPolicyTestCase,
    SuspendedCleanupTestCase,
)
from tests.unit.src.sqlbuild.runtime.execution_limits.helpers import (
    FakeCancellingAdapter,
    FakeRefusingAdapter,
    run_finished_statement,
    run_statement_until_cancelled,
)

_ONE_SECOND: ItemTimeoutPolicy = ItemTimeoutPolicy(limit="1s", seconds=1, source="test")
_EXPIRED: ItemTimeoutPolicy = ItemTimeoutPolicy(limit="1s", seconds=0, source="test")


@pytest.mark.parametrize(
    "test_case",
    [
        DeadlineCancellationTestCase(
            description="synchronous cancel stops the statement",
            interrupt_result=True,
            adapter_type=FakeCancellingAdapter,
            asynchronous=False,
            statement_query_id="query-1",
            expected_outcome=CancellationOutcome.CONFIRMED,
        ),
        DeadlineCancellationTestCase(
            description="asynchronous cancel is reported unknown",
            interrupt_result=True,
            adapter_type=FakeCancellingAdapter,
            asynchronous=True,
            statement_query_id="query-1",
            expected_outcome=CancellationOutcome.UNKNOWN,
        ),
        DeadlineCancellationTestCase(
            description="adapter without cancellation is reported unsupported",
            interrupt_result=False,
            adapter_type=FakeCancellingAdapter,
            asynchronous=False,
            statement_query_id=None,
            expected_outcome=CancellationOutcome.UNSUPPORTED,
        ),
        DeadlineCancellationTestCase(
            description="cancel request error is reported failed",
            interrupt_result=True,
            adapter_type=FakeRefusingAdapter,
            asynchronous=False,
            statement_query_id=None,
            expected_outcome=CancellationOutcome.FAILED,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_running_statement_when_item_deadline_expires_then_cancellation_outcome_is_reported(
    test_case: DeadlineCancellationTestCase,
) -> None:
    adapter: FakeCancellingAdapter = test_case.adapter_type(
        result=test_case.interrupt_result, asynchronous=test_case.asynchronous
    )

    with item_deadline_scope(
        kind=ItemKind.TEST,
        name="orders_rollup",
        policy=_ONE_SECOND,
        adapter=adapter,
        connection=None,
    ) as deadline:
        run_statement_until_cancelled(
            adapter=adapter, finished_query_id=test_case.statement_query_id
        )

    assert isinstance(deadline, ItemDeadline)
    assert deadline.expired
    report: ItemTimeoutReport = deadline.report()
    assert report.cancellation == test_case.expected_outcome
    assert "query-1" in report.query_ids
    assert report.source == "test"


@pytest.mark.parametrize(
    "test_case",
    [
        IdleExpiryTestCase(
            description="model past its limit between statements",
            kind=ItemKind.MODEL,
            statements_run=1,
            expected_expired=True,
            expected_outcome=CancellationOutcome.NOT_NEEDED,
            expected_interrupted=False,
        ),
        IdleExpiryTestCase(
            description="rendering before the first statement does not count",
            kind=ItemKind.TEST,
            statements_run=0,
            expected_expired=False,
            expected_outcome=CancellationOutcome.NOT_NEEDED,
            expected_interrupted=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_no_running_statement_when_limit_passes_then_only_started_items_expire(
    test_case: IdleExpiryTestCase,
) -> None:
    adapter: FakeCancellingAdapter = FakeCancellingAdapter(result=True, asynchronous=False)

    with item_deadline_scope(
        kind=test_case.kind, name="orders", policy=_ONE_SECOND, adapter=adapter, connection=None
    ) as deadline:
        for _ in range(test_case.statements_run):
            run_finished_statement()
        time.sleep(1.1)
        with contextlib.suppress(ItemTimeoutError):
            enforce_execution_deadline()

    assert isinstance(deadline, ItemDeadline)
    assert deadline.expired == test_case.expected_expired
    assert adapter.interrupted.is_set() == test_case.expected_interrupted
    assert deadline.report().cancellation == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    [
        NestedDeadlineTestCase(
            description="enclosing model limit cancels a test statement inside it",
            outer_seconds=1,
            inner_seconds=3600,
            expected_expired_name="orders_model",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_nested_deadlines_when_enclosing_one_expires_then_inner_statement_is_cancelled(
    test_case: NestedDeadlineTestCase,
) -> None:
    adapter: FakeCancellingAdapter = FakeCancellingAdapter(result=True, asynchronous=False)

    with item_deadline_scope(
        kind=ItemKind.MODEL,
        name="orders_model",
        policy=ItemTimeoutPolicy(
            limit=f"{test_case.outer_seconds}s", seconds=test_case.outer_seconds, source="test"
        ),
        adapter=adapter,
        connection=None,
    ) as outer:
        with item_deadline_scope(
            kind=ItemKind.TEST,
            name="orders_test",
            policy=ItemTimeoutPolicy(
                limit=f"{test_case.inner_seconds}s", seconds=test_case.inner_seconds, source="test"
            ),
            adapter=adapter,
            connection=None,
        ) as inner:
            assert inner is not None
            assert inner.remaining_seconds <= test_case.outer_seconds
            run_statement_until_cancelled(adapter=adapter, finished_query_id=None)
            with pytest.raises(ItemTimeoutError) as raised:
                enforce_execution_deadline()

    assert outer is not None
    assert outer.expired
    assert test_case.expected_expired_name in str(raised.value)


@pytest.mark.parametrize(
    "test_case",
    [
        HeldClockTestCase(
            description="queued or cleanup time is not running time",
            held_seconds=0.3,
            expected_maximum_running_seconds=0.2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_held_clock_when_time_passes_then_running_time_excludes_it(
    test_case: HeldClockTestCase,
) -> None:
    adapter: FakeCancellingAdapter = FakeCancellingAdapter(result=True, asynchronous=False)

    with item_deadline_scope(
        kind=ItemKind.TEST, name="orders", policy=_ONE_SECOND, adapter=adapter, connection=None
    ) as deadline:
        assert deadline is not None
        run_finished_statement()
        deadline.hold()
        time.sleep(test_case.held_seconds)
        deadline.release()
        running: float = deadline.running_seconds()

    assert running < test_case.expected_maximum_running_seconds


@pytest.mark.parametrize(
    "test_case",
    [SuspendedCleanupTestCase(description="cleanup after expiry", expected_enforced=True)],
    ids=lambda case: case.description,
)
def test_given_expired_item_when_suspended_for_cleanup_then_statements_are_allowed(
    test_case: SuspendedCleanupTestCase,
) -> None:
    adapter: FakeCancellingAdapter = FakeCancellingAdapter(result=True, asynchronous=False)

    with item_deadline_scope(
        kind=ItemKind.TEST, name="orders", policy=_EXPIRED, adapter=adapter, connection=None
    ):
        run_finished_statement()
        time.sleep(0.05)
        with execution_deadlines_suspended():
            enforce_execution_deadline()
            enforced: bool = True

    assert enforced == test_case.expected_enforced


@pytest.mark.parametrize(
    "test_case",
    [
        EarliestDeadlineTestCase(
            description="item expires first",
            build_seconds=3600,
            item_seconds=1,
            expected_item_is_current=True,
        ),
        EarliestDeadlineTestCase(
            description="build expires first",
            build_seconds=1,
            item_seconds=3600,
            expected_item_is_current=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_build_and_item_deadlines_when_reading_current_then_earliest_expiry_applies(
    test_case: EarliestDeadlineTestCase,
) -> None:
    adapter: FakeCancellingAdapter = FakeCancellingAdapter(result=True, asynchronous=False)

    with (
        execution_deadline_scope(
            max_duration_seconds=test_case.build_seconds,
            max_duration=f"{test_case.build_seconds}s",
            target_name="dev",
            remediation=None,
        ),
        item_deadline_scope(
            kind=ItemKind.TEST,
            name="orders",
            policy=ItemTimeoutPolicy(
                limit=f"{test_case.item_seconds}s", seconds=test_case.item_seconds, source="test"
            ),
            adapter=adapter,
            connection=None,
        ),
    ):
        current: object = current_execution_deadline()

    assert isinstance(current, ItemDeadline) == test_case.expected_item_is_current


@pytest.mark.parametrize(
    "test_case",
    [NoPolicyTestCase(description="no configured limit", expected_deadline=None)],
    ids=lambda case: case.description,
)
def test_given_no_policy_when_entering_scope_then_no_deadline_applies(
    test_case: NoPolicyTestCase,
) -> None:
    adapter: FakeCancellingAdapter = FakeCancellingAdapter(result=True, asynchronous=False)

    with item_deadline_scope(
        kind=ItemKind.TEST, name="orders", policy=None, adapter=adapter, connection=None
    ) as deadline:
        current: object = current_execution_deadline()

    assert deadline is test_case.expected_deadline
    assert current is test_case.expected_deadline


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
