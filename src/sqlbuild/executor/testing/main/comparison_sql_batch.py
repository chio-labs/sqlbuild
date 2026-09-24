"""Build batches of executable SQL unit-test comparison queries natively."""

from __future__ import annotations

from typing import Any, cast

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.planner.main.execution.sql_test_dialect import (
    restore_sql_test_dialect_function_names,
)
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.testing._helpers.native_requests import comparison_request
from sqlbuild.executor.testing.constants import SQL_TEST_NATIVE_RENDER_WORKERS
from sqlbuild.executor.testing.exceptions import SqlTestRenderingError
from sqlbuild.executor.testing.types import NativeSqlTestRenderingModule


def build_sql_test_comparison_sql_batch(
    *,
    test_entries: tuple[SqlTestPlanEntry, ...],
    set_difference_operator: str = "EXCEPT",
    sql_analysis_dialect: str | None = None,
) -> tuple[str, ...]:
    """Build comparison SQL for a deterministic batch of planned SQL tests."""

    if not test_entries:
        return ()
    requests: list[dict[str, object]] = [
        comparison_request(
            test_entry=test_entry,
            set_difference_operator=set_difference_operator,
            sql_analysis_dialect=sql_analysis_dialect,
        )
        for test_entry in test_entries
    ]
    response: object = orjson.loads(
        cast(NativeSqlTestRenderingModule, _native).render_sql_test_comparisons_json(
            orjson.dumps(
                {"requests": requests, "workers": SQL_TEST_NATIVE_RENDER_WORKERS},
                option=orjson.OPT_SORT_KEYS,
            ).decode()
        )
    )
    if not isinstance(response, list) or len(response) != len(test_entries):
        raise SqlTestRenderingError("native SQL-test rendering returned an invalid batch response")
    rendered: list[str] = []
    for item in response:
        item_dict: dict[str, Any] | None = (
            cast(dict[str, Any], item) if isinstance(item, dict) else None
        )
        sql: object = item_dict.get("sql") if item_dict is not None else None
        if not isinstance(sql, str):
            raise SqlTestRenderingError("native SQL-test rendering returned an invalid result")
        rendered.append(
            restore_sql_test_dialect_function_names(
                sql=sql,
                dialect=sql_analysis_dialect,
            )
        )
    return tuple(rendered)
