import inspect
from typing import Any, ClassVar

import pytest

from sqlbuild.adapter.contract.classes.connection import ConnectionMixin
from sqlbuild.adapter.contract.models import QueryResult
from tests.unit.src.sqlbuild.adapter.contract.classes.connection._test_types import (
    ConnectionContractCase,
    SqlExecutionFailureCase,
)


class _LegacyExecuteOnlyAdapter(ConnectionMixin):
    adapter_name: ClassVar[str] = "legacy"

    def connect(self, config: dict[str, Any]) -> Any:
        return config

    def execute(self, *, connection: Any, sql: str) -> Any:
        del connection
        return sql

    def query(self, *, connection: Any, sql: str, limit: int | None) -> QueryResult:
        del connection, sql, limit
        return QueryResult()

    def close(self, connection: Any) -> None:
        del connection


class _ProtectedExecuteAdapter(ConnectionMixin):
    adapter_name: ClassVar[str] = "protected"

    def connect(self, config: dict[str, Any]) -> Any:
        return config

    def _execute(self, *, connection: Any, sql: str) -> Any:
        del connection
        return sql

    def query(self, *, connection: Any, sql: str, limit: int | None) -> QueryResult:
        del connection, sql, limit
        return QueryResult()

    def close(self, connection: Any) -> None:
        del connection


class _FailingExecuteAdapter(_ProtectedExecuteAdapter):
    def _execute(self, *, connection: Any, sql: str) -> Any:
        del connection, sql
        raise ValueError("warehouse rejected statement")


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionContractCase(
            description="legacy public execute does not satisfy protected hook",
            expected_abstract=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_legacy_execute_only_subclass_when_checked_then_it_remains_abstract(
    test_case: ConnectionContractCase,
) -> None:
    assert inspect.isabstract(_LegacyExecuteOnlyAdapter) is test_case.expected_abstract
    with pytest.raises(TypeError, match="_execute"):
        _LegacyExecuteOnlyAdapter()


@pytest.mark.parametrize(
    "test_case",
    [
        ConnectionContractCase(
            description="protected execute satisfies adapter contract",
            expected_abstract=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_protected_execute_subclass_when_constructed_then_it_is_concrete(
    test_case: ConnectionContractCase,
) -> None:
    adapter: _ProtectedExecuteAdapter = _ProtectedExecuteAdapter()

    assert inspect.isabstract(_ProtectedExecuteAdapter) is test_case.expected_abstract
    assert adapter.execute(connection=object(), sql="SELECT 1") == "SELECT 1"


@pytest.mark.parametrize(
    "test_case",
    (
        SqlExecutionFailureCase(
            description="warehouse execute failure retains exact SQL",
            sql="CREATE TABLE staged_orders AS SELECT * FROM raw_orders",
            expected_error="warehouse rejected statement",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_warehouse_failure_when_executing_then_exact_sql_is_attributed(
    test_case: SqlExecutionFailureCase,
) -> None:
    adapter: _FailingExecuteAdapter = _FailingExecuteAdapter()

    with pytest.raises(ValueError) as exc_info:
        adapter.execute(connection=object(), sql=test_case.sql)

    assert vars(exc_info.value)["failed_sql"] == test_case.sql
    assert str(exc_info.value) == test_case.expected_error
