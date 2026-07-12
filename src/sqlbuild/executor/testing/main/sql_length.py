"""SQL length guardrails for lightweight SQL unit tests."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.exceptions import CompileInputError


def validate_unit_test_sql_length(
    *,
    sql: str,
    adapter: BaseAdapter,
    test_name: str,
) -> None:
    limit: int | None = adapter.recommended_max_sql_length()
    if limit is None:
        return
    actual_length: int = len(sql)
    if actual_length <= limit:
        return
    raise CompileInputError(
        _format_unit_test_sql_length_error(
            sql=sql,
            adapter=adapter,
            test_name=test_name,
        )
    )


def _format_unit_test_sql_length_error(
    *,
    sql: str,
    adapter: BaseAdapter,
    test_name: str,
) -> str:
    limit: int | None = adapter.recommended_max_sql_length()
    actual_length: int = len(sql)
    if limit is None:
        return (
            f"Combined unit test SQL for '{test_name}' is {actual_length} characters, "
            "which exceeds this adapter's configured recommendation. "
            "This test is too large for a single lightweight unit query. "
            "Consider splitting it into smaller unit tests or moving it to a scenario test."
        )
    return (
        f"Combined unit test SQL for '{test_name}' is {actual_length} characters, "
        f"which exceeds the recommended maximum of {limit} for this adapter. "
        "This test is too large for a single lightweight unit query. "
        "Consider splitting it into smaller unit tests or moving it to a scenario test."
    )
