import inspect
from typing import Any, ClassVar

import pytest

from sqlbuild.adapter.contract.classes.connection import ConnectionMixin
from sqlbuild.adapter.contract.models import QueryResult
from tests.unit.src.sqlbuild.adapter.contract.classes.connection._test_types import (
    ConnectionContractCase,
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
