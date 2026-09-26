"""SQL length guardrails for lightweight SQL unit tests."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.types import StatementSizeLimit
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.executor.testing.constants import SQL_TEST_SIZE_BYTES


def validate_unit_test_sql_length(
    *,
    sql: str,
    adapter: BaseAdapter,
    test_name: str,
    model_name: str,
) -> None:
    size_limit: StatementSizeLimit | None = adapter.max_statement_size()
    if size_limit is None:
        return
    limit, unit = size_limit
    actual_length: int = len(sql.encode("utf-8")) if unit == SQL_TEST_SIZE_BYTES else len(sql)
    if actual_length <= limit:
        return
    raise CompileInputError(
        f"Combined unit test SQL for '{test_name}' including '{model_name}' "
        f"is {actual_length} {unit}, which exceeds the maximum of {limit} {unit} "
        "for this adapter. Consider splitting it into smaller unit tests or moving it "
        "to a scenario test."
    )
