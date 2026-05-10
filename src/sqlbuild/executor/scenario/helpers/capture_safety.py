"""Safety helpers for scenario snapshot capture."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import QueryResult
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCaptureRelationPlan,
)
from sqlbuild.shared.constants import (
    SCENARIO_EXEC_CAPTURE_INTERNAL,
    SCENARIO_EXEC_CAPTURE_LIMIT_EXCEEDED,
)


def query_capture_relation_row_count(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relation_plan: ScenarioSnapshotCaptureRelationPlan,
    source_relation_name: str,
) -> int:
    """Return a preflight row count for one materialized snapshot relation."""

    query_result: QueryResult = adapter.query(
        connection,
        f"SELECT COUNT(*) FROM {source_relation_name}",
        limit=1,
    )
    if len(query_result.rows) != 1 or len(query_result.rows[0]) != 1:
        error: ValueError = ValueError(
            f"row count query did not return one value for relation '{relation_plan.logical_name}'"
        )
        object.__setattr__(error, "code", SCENARIO_EXEC_CAPTURE_INTERNAL)
        raise error
    row_count_value: object = query_result.rows[0][0]
    if not isinstance(row_count_value, int | Decimal | str):
        error = ValueError(
            "row count query returned a non-numeric value for relation "
            f"'{relation_plan.logical_name}'"
        )
        object.__setattr__(error, "code", SCENARIO_EXEC_CAPTURE_INTERNAL)
        raise error
    return int(row_count_value)


def validate_capture_row_limits(
    *,
    scenario_name: str,
    relation_plan: ScenarioSnapshotCaptureRelationPlan,
    relation_row_count: int,
    total_row_count: int,
    limits: ScenarioSnapshotCaptureLimits,
) -> None:
    """Fail if relation or total row counts exceed configured capture limits."""

    if (
        limits.max_rows_per_relation is not None
        and relation_row_count > limits.max_rows_per_relation
    ):
        raise_capture_limit_error(
            "Scenario "
            f"'{scenario_name}' {relation_plan.kind.value} '{relation_plan.logical_name}' "
            f"has {relation_row_count} rows, exceeding the per-relation capture limit "
            f"of {limits.max_rows_per_relation} rows"
        )
    if (
        limits.max_total_rows is not None
        and total_row_count + relation_row_count > limits.max_total_rows
    ):
        raise_capture_limit_error(
            f"Scenario '{scenario_name}' would capture {total_row_count + relation_row_count} "
            f"total rows, exceeding the total capture limit of {limits.max_total_rows} rows"
        )


def max_relation_write_bytes(
    *,
    total_byte_count: int,
    limits: ScenarioSnapshotCaptureLimits,
) -> int | None:
    """Return the effective JSONL byte cap for the next relation write."""

    if limits.force:
        return None
    candidates: list[int] = []
    if limits.max_bytes_per_relation is not None:
        candidates.append(limits.max_bytes_per_relation)
    if limits.max_total_bytes is not None:
        candidates.append(max(0, limits.max_total_bytes - total_byte_count))
    if not candidates:
        return None
    return min(candidates)


def capture_error_help(error_code: str) -> str:
    """Return user help for a capture failure code."""

    if error_code == SCENARIO_EXEC_CAPTURE_LIMIT_EXCEEDED:
        return "Narrow the scenario fixture query, raise the snapshot limit, or rerun with --force."
    return (
        "Check the materialized scenario input relation and rerun capture with "
        "--retain to inspect warehouse artifacts."
    )


def raise_capture_limit_error(message: str) -> None:
    """Raise a coded capture limit error."""

    error: ValueError = ValueError(message)
    object.__setattr__(error, "code", SCENARIO_EXEC_CAPTURE_LIMIT_EXCEEDED)
    raise error
