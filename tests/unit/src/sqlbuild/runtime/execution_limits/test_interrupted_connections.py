"""Interrupted-connection marks match only the connection that was interrupted."""

from __future__ import annotations

import pytest

from sqlbuild.runtime.execution_limits.classes.interrupted_connections import (
    InterruptedConnections,
)
from tests.unit.src.sqlbuild.runtime.execution_limits._test_types import (
    InterruptedConnectionReportsTestCase,
    InterruptedIdentityReuseTestCase,
)
from tests.unit.src.sqlbuild.runtime.execution_limits.helpers import PlaceholderConnection


@pytest.mark.parametrize(
    "test_case",
    [
        InterruptedConnectionReportsTestCase(
            description="weakly referenced connection is reported once",
            new_connection=PlaceholderConnection,
            expected_reports=(True, False),
        ),
        InterruptedConnectionReportsTestCase(
            description="connection without weak references is reported once",
            new_connection=object,
            expected_reports=(True, False),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_marked_connection_when_checked_twice_then_reported_once(
    test_case: InterruptedConnectionReportsTestCase,
) -> None:
    connections: InterruptedConnections = InterruptedConnections()
    connection: object = test_case.new_connection()
    connections.mark(connection)

    reports: tuple[bool, bool] = (connections.take(connection), connections.take(connection))

    assert reports == test_case.expected_reports


@pytest.mark.parametrize(
    "test_case",
    [
        InterruptedIdentityReuseTestCase(
            description="new connection at a collected interrupted identity is not reported",
            expected_reuse_and_report=(True, False),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_collected_marked_connection_when_new_connection_reuses_identity_then_not_reported(
    test_case: InterruptedIdentityReuseTestCase,
) -> None:
    connections: InterruptedConnections = InterruptedConnections()
    interrupted: PlaceholderConnection = PlaceholderConnection()
    interrupted_identity: int = id(interrupted)
    connections.mark(interrupted)
    del interrupted

    reused: PlaceholderConnection = PlaceholderConnection()

    assert (
        id(reused) == interrupted_identity,
        connections.take(reused),
    ) == test_case.expected_reuse_and_report
