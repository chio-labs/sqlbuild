"""Postgres transactions and unit test outputs under per-item deadlines."""

from __future__ import annotations

import threading

import pytest

from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.postgres.classes.postgres_connection import _PostgresConnection
from sqlbuild.runtime.execution_limits.exceptions import ItemTimeoutError
from sqlbuild.runtime.execution_limits.main.item_deadline_scope import item_deadline_scope
from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy
from sqlbuild.runtime.execution_limits.types import ItemKind
from tests.unit.src.sqlbuild.adapters.helpers import (
    CancellableRawConnection,
    expire_after_start,
    without_limits,
)
from tests.unit.src.sqlbuild.adapters.postgres._test_types import (
    DeadlineTransactionTestCase,
    FailedSqlTestOutputTestCase,
    SqlTestOutputTransactionTestCase,
)

_POLICY: ItemTimeoutPolicy = ItemTimeoutPolicy(limit="60s", seconds=60, source="test")
_OUTPUT: str = "__sqb_test_output_abc_0"


@pytest.mark.parametrize(
    "test_case",
    [
        DeadlineTransactionTestCase(
            description="expiry mid-promotion rolls back before the timeout propagates",
            expected_statements=(
                "BEGIN",
                "ALTER TABLE orders RENAME TO orders__prev",
                "ROLLBACK",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_expired_model_deadline_in_transaction_when_failing_then_rollback_runs_first(
    test_case: DeadlineTransactionTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    raw: CancellableRawConnection = CancellableRawConnection()
    connection: _PostgresConnection = _PostgresConnection(raw)

    with item_deadline_scope(
        kind=ItemKind.MODEL, name="orders", policy=_POLICY, adapter=adapter, connection=connection
    ) as deadline:
        assert deadline is not None
        with pytest.raises(ItemTimeoutError), adapter.transaction(connection):
            _ = adapter.execute(
                connection=connection, sql="ALTER TABLE orders RENAME TO orders__prev"
            )
            deadline.expire()
            _ = adapter.execute(
                connection=connection, sql="ALTER TABLE orders__next RENAME TO orders"
            )

    assert without_limits(raw.executed) == test_case.expected_statements
    assert not any(sql.startswith("SET statement_timeout") for sql in raw.executed)
    assert not connection.in_transaction()


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestOutputTransactionTestCase(
            description="test opens and ends its own transaction",
            setup_statements=(),
            expected_in_transaction=False,
            expected_statements=(
                "BEGIN",
                f"CREATE TEMPORARY TABLE {_OUTPUT} ON COMMIT DROP AS SELECT 1 AS order_id",
                f"SELECT * FROM {_OUTPUT}",
                "ROLLBACK",
            ),
        ),
        SqlTestOutputTransactionTestCase(
            description="caller transaction is kept and the output dropped inside it",
            setup_statements=("BEGIN",),
            expected_in_transaction=True,
            expected_statements=(
                "BEGIN",
                f"CREATE TEMPORARY TABLE {_OUTPUT} ON COMMIT DROP AS SELECT 1 AS order_id",
                f"SELECT * FROM {_OUTPUT}",
                f"DROP TABLE IF EXISTS {_OUTPUT}",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_test_output_when_stored_and_released_then_one_transaction_holds_it(
    test_case: SqlTestOutputTransactionTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    raw: CancellableRawConnection = CancellableRawConnection()
    connection: _PostgresConnection = _PostgresConnection(raw)
    for statement in test_case.setup_statements:
        _ = adapter.execute(connection=connection, sql=statement)

    stored: str | None = adapter.create_sql_test_output(
        connection=connection, sql="SELECT 1 AS order_id", name=_OUTPUT
    )
    assert stored is not None
    relation: str = stored
    _ = adapter.execute(connection=connection, sql=f"SELECT * FROM {relation}")
    adapter.drop_sql_test_output(connection=connection, relation=relation)

    assert without_limits(raw.executed) == test_case.expected_statements
    assert connection.in_transaction() is test_case.expected_in_transaction


@pytest.mark.parametrize(
    "test_case",
    [
        FailedSqlTestOutputTestCase(
            description="failed output creation ends the test's transaction",
            expected_statements=("BEGIN", f"CREATE TEMPORARY TABLE {_OUTPUT} ON COMMIT DROP AS "),
            expected_in_transaction=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_output_query_when_storing_then_transaction_is_rolled_back(
    test_case: FailedSqlTestOutputTestCase,
) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    raw: CancellableRawConnection = CancellableRawConnection()
    connection: _PostgresConnection = _PostgresConnection(raw)
    failing_query: str = "SELECT * FROM orders"

    with item_deadline_scope(
        kind=ItemKind.TEST, name="orders", policy=_POLICY, adapter=adapter, connection=connection
    ) as deadline:
        assert deadline is not None
        watchdog: threading.Thread = expire_after_start(deadline=deadline, raw=raw)
        with pytest.raises(ItemTimeoutError):
            _ = adapter.create_sql_test_output(
                connection=connection, sql=failing_query, name=_OUTPUT
            )
        watchdog.join(timeout=5)

    statements: tuple[str, ...] = without_limits(raw.executed)
    assert statements[:2] == (
        test_case.expected_statements[0],
        test_case.expected_statements[1] + failing_query,
    )
    assert statements[-1] == "ROLLBACK"
    assert connection.in_transaction() is test_case.expected_in_transaction


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
