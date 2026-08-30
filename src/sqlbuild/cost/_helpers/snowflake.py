"""Snowflake query-history cost collection."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from polyglot_sql import CreateTable, CreateView, ParseError, parse_one

from sqlbuild.cost._helpers.allocation import allocate_run_cost
from sqlbuild.cost._helpers.ledger import read_statement_ledger
from sqlbuild.cost.constants import (
    COST_TELEMETRY_HEALTH,
    INCOMPLETE_HISTORY_REASON,
    LEDGER_PERSISTENCE_FAILURE_LIMITATION_PREFIX,
    MISSING_WAREHOUSE_METADATA_REASON,
    NO_WAREHOUSE_COMPUTE_REASON,
    RUNNING_EXECUTION_STATUS,
    SQLBUILD_QUERY_TAG_APP,
)
from sqlbuild.cost.models import (
    QueryCostObservation,
    RunCostSummary,
    StatementLedgerEntry,
)
from sqlbuild.cost.types import CostStatus

_RESULT_LIMIT: int = 10_000
_MINIMUM_SPLIT_WINDOW: timedelta = timedelta(milliseconds=1)
_COLLECTION_DEADLINE_SECONDS: float = 10.0
_QUERY_TIMEOUT_SECONDS: str = "5"
_QUERY_HISTORY_RETENTION: timedelta = timedelta(days=7)
_MAXIMUM_CLOCK_SKEW: timedelta = timedelta(minutes=10)
_USE_QUERY_TYPE: str = "USE"
_DROP_QUERY_TYPE: str = "DROP"
_CREATE_QUERY_TYPE: str = "CREATE"
_DYNAMIC_TABLE_MODIFIER: str = "DYNAMIC"
_HOOK_RESOURCE_TYPE: str = "hook"
_VISIBLE_QUERY_LIMITATION: str = (
    "Concurrency sharing includes only queries visible to the executing Snowflake role."
)
_INCOMPLETE_OBSERVATION_REASONS: frozenset[str] = frozenset(
    {MISSING_WAREHOUSE_METADATA_REASON, INCOMPLETE_HISTORY_REASON}
)


def collect_snowflake_run_cost(
    *,
    connection: Any,
    database: str | None = None,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    statement_ledger_path: Path,
    usd_per_credit: Decimal,
    rate_source: str,
    attempts: int = 3,
    retry_delay_seconds: float = 1.0,
) -> RunCostSummary:
    """Collect visible history and attribute exact ledger query IDs to one run."""

    deadline: float = time.monotonic() + _COLLECTION_DEADLINE_SECONDS
    ledger: tuple[StatementLedgerEntry, ...] = read_statement_ledger(
        path=statement_ledger_path,
        run_id=run_id,
    )
    ledger_failure: str | None = COST_TELEMETRY_HEALTH.consume_ledger_failure(run_id=run_id)
    ledger_by_query_id: dict[str, StatementLedgerEntry] = {
        entry.query_id: entry for entry in ledger if entry.query_id is not None
    }
    expected_query_ids: frozenset[str] = frozenset(ledger_by_query_id)
    classification_query_ids: frozenset[str] = frozenset(
        query_id
        for query_id, entry in ledger_by_query_id.items()
        if entry.resource_type != _HOOK_RESOURCE_TYPE
    )
    if ledger and not expected_query_ids:
        no_query_id_summary: RunCostSummary = _apply_ledger_failure(
            summary=_partial_summary(
                usd_per_credit=usd_per_credit,
                rate_source=rate_source,
                message="No Snowflake query IDs were available in the statement ledger.",
            ),
            ledger_failure=ledger_failure,
        )
        return replace(
            no_query_id_summary,
            expected_statement_count=len(ledger),
            missing_statement_count=len(ledger),
        )

    summary: RunCostSummary | None = None
    observed_query_ids: frozenset[str] = frozenset()
    skipped_reasons: dict[str, str] = {}
    saturated = False
    for attempt in range(attempts):
        observations, observed_query_ids, skipped_reasons, saturated = _query_observations(
            connection=connection,
            database=database,
            started_at=started_at,
            completed_at=completed_at,
            expected_query_ids=expected_query_ids,
            classification_query_ids=classification_query_ids,
            deadline=deadline,
        )
        attributed_observations: tuple[QueryCostObservation, ...] = tuple(
            _attribute_from_ledger(observation=observation, ledger=ledger_by_query_id)
            for observation in observations
        )
        summary = allocate_run_cost(
            observations=attributed_observations,
            run_id=run_id,
            usd_per_credit=usd_per_credit,
            rate_source=rate_source,
            result_limit_reached=saturated,
        )
        summary = replace(
            summary,
            limitations=tuple(sorted({*summary.limitations, _VISIBLE_QUERY_LIMITATION})),
        )
        if expected_query_ids.issubset(observed_query_ids) and not _has_incomplete_observation(
            expected_query_ids=expected_query_ids,
            skipped_reasons=skipped_reasons,
        ):
            summary = _apply_observation_gaps(
                summary=summary,
                expected_statement_count=len(ledger),
                expected_query_ids=expected_query_ids,
                observed_query_ids=observed_query_ids,
                skipped_reasons=skipped_reasons,
            )
            if summary.status == CostStatus.PENDING:
                summary = replace(
                    summary,
                    status=CostStatus.COMPLETE,
                    message="No cost-bearing Snowflake warehouse queries were observed.",
                )
            return _apply_ledger_failure(summary=summary, ledger_failure=ledger_failure)
        if attempt + 1 < attempts:
            remaining_seconds: float = deadline - time.monotonic()
            if remaining_seconds <= retry_delay_seconds:
                break
            time.sleep(retry_delay_seconds)

    if summary is None:
        summary = _partial_summary(
            usd_per_credit=usd_per_credit,
            rate_source=rate_source,
            message="Snowflake query history could not be collected.",
        )
    missing_count: int = len(expected_query_ids.difference(observed_query_ids))
    limitations: set[str] = set(summary.limitations)
    if missing_count:
        limitations.add(
            f"{missing_count} statement ledger query ID(s) were not visible in query history."
        )
    if saturated:
        limitations.add("Snowflake query-history result limit was reached.")
    visible_expected_query_ids: frozenset[str] = expected_query_ids.intersection(observed_query_ids)
    history_expired: bool = datetime.now(UTC) - completed_at >= _QUERY_HISTORY_RETENTION
    final_status: CostStatus
    if history_expired and not visible_expected_query_ids:
        final_status = CostStatus.UNAVAILABLE
        message = "Snowflake query history is no longer available for this run."
    elif not visible_expected_query_ids and not saturated:
        final_status = CostStatus.PENDING
        message = "Snowflake query history is not complete yet. Run `sqb cost latest` to refresh."
    else:
        final_status = CostStatus.PARTIAL
        message = summary.message or "Snowflake query history was only partially available."
    summary = _apply_observation_gaps(
        summary=replace(
            summary,
            status=final_status,
            limitations=tuple(sorted(limitations)),
            message=message,
        ),
        expected_statement_count=len(ledger),
        expected_query_ids=expected_query_ids,
        observed_query_ids=observed_query_ids,
        skipped_reasons=skipped_reasons,
    )
    return _apply_ledger_failure(
        summary=summary,
        ledger_failure=ledger_failure,
    )


def _query_observations(
    *,
    connection: Any,
    database: str | None = None,
    started_at: datetime,
    completed_at: datetime,
    expected_query_ids: frozenset[str],
    classification_query_ids: frozenset[str],
    deadline: float,
) -> tuple[
    tuple[QueryCostObservation, ...],
    frozenset[str],
    dict[str, str],
    bool,
]:
    open_rows: tuple[tuple[Any, ...], ...] = _query_open_history_rows(
        connection=connection,
        database=database,
        started_at=started_at - _MAXIMUM_CLOCK_SKEW,
        classification_query_ids=classification_query_ids,
        deadline=deadline,
    )
    saturated: bool = len(open_rows) >= _RESULT_LIMIT
    if saturated:
        bounded_rows, bounded_saturated = _query_history_rows(
            connection=connection,
            database=database,
            started_at=started_at - _MAXIMUM_CLOCK_SKEW,
            completed_at=completed_at + _MAXIMUM_CLOCK_SKEW,
            classification_query_ids=classification_query_ids,
            deadline=deadline,
        )
        rows_by_query_id: dict[str, tuple[Any, ...]] = {
            str(row[0]): row for row in open_rows if _is_running_history_row(row=row)
        }
        rows_by_query_id.update({str(row[0]): row for row in bounded_rows})
        rows: tuple[tuple[Any, ...], ...] = tuple(
            rows_by_query_id[key] for key in sorted(rows_by_query_id)
        )
        saturated = bounded_saturated
    else:
        rows = open_rows
    observations: list[QueryCostObservation] = []
    observed_query_ids: set[str] = set()
    skipped_reasons: dict[str, str] = {}
    for row in rows:
        query_id: str = str(row[0])
        observed_query_ids.add(query_id)
        observation, skip_reason = _row_to_observation(
            row=row,
            require_complete=query_id in expected_query_ids,
        )
        if observation is not None:
            observations.append(observation)
        elif skip_reason is not None:
            skipped_reasons[query_id] = skip_reason
    observations.sort(key=lambda item: (item.started_at, item.query_id))
    return tuple(observations), frozenset(observed_query_ids), skipped_reasons, saturated


def _is_running_history_row(*, row: tuple[Any, ...]) -> bool:
    return row[7] is None or str(row[10]).upper() == RUNNING_EXECUTION_STATUS


def _query_open_history_rows(
    *,
    connection: Any,
    database: str | None = None,
    started_at: datetime,
    classification_query_ids: frozenset[str],
    deadline: float,
) -> tuple[tuple[Any, ...], ...]:
    if time.monotonic() >= deadline:
        raise TimeoutError("Snowflake cost collection deadline exceeded")
    cursor: Any = connection.execute(
        _render_open_query_history_sql(
            database=database,
            started_at=started_at,
            classification_query_ids=classification_query_ids,
        ),
        statement_params={"STATEMENT_TIMEOUT_IN_SECONDS": _QUERY_TIMEOUT_SECONDS},
    )
    if time.monotonic() >= deadline:
        raise TimeoutError("Snowflake cost collection deadline exceeded")
    rows: tuple[tuple[Any, ...], ...] = tuple(tuple(row) for row in cursor.fetchall())
    if time.monotonic() >= deadline:
        raise TimeoutError("Snowflake cost collection deadline exceeded")
    return rows


def _query_history_rows(
    *,
    connection: Any,
    database: str | None = None,
    started_at: datetime,
    completed_at: datetime,
    classification_query_ids: frozenset[str],
    deadline: float,
) -> tuple[tuple[tuple[Any, ...], ...], bool]:
    if time.monotonic() >= deadline:
        raise TimeoutError("Snowflake cost collection deadline exceeded")
    cursor: Any = connection.execute(
        _render_query_history_sql(
            database=database,
            started_at=started_at,
            completed_at=completed_at,
            classification_query_ids=classification_query_ids,
        ),
        statement_params={"STATEMENT_TIMEOUT_IN_SECONDS": _QUERY_TIMEOUT_SECONDS},
    )
    if time.monotonic() >= deadline:
        raise TimeoutError("Snowflake cost collection deadline exceeded")
    rows: tuple[tuple[Any, ...], ...] = tuple(tuple(row) for row in cursor.fetchall())
    if time.monotonic() >= deadline:
        raise TimeoutError("Snowflake cost collection deadline exceeded")
    if len(rows) < _RESULT_LIMIT:
        return rows, False
    if completed_at - started_at <= _MINIMUM_SPLIT_WINDOW:
        return rows, True

    midpoint: datetime = started_at + (completed_at - started_at) / 2
    left_rows, left_saturated = _query_history_rows(
        connection=connection,
        database=database,
        started_at=started_at,
        completed_at=midpoint,
        classification_query_ids=classification_query_ids,
        deadline=deadline,
    )
    right_rows, right_saturated = _query_history_rows(
        connection=connection,
        database=database,
        started_at=midpoint,
        completed_at=completed_at,
        classification_query_ids=classification_query_ids,
        deadline=deadline,
    )
    rows_by_query_id: dict[str, tuple[Any, ...]] = {
        str(row[0]): row for row in (*left_rows, *right_rows)
    }
    merged_rows: tuple[tuple[Any, ...], ...] = tuple(
        rows_by_query_id[key] for key in sorted(rows_by_query_id)
    )
    return merged_rows, left_saturated or right_saturated


def _row_to_observation(
    *,
    row: tuple[Any, ...],
    require_complete: bool,
) -> tuple[QueryCostObservation | None, str | None]:
    (
        query_id,
        query_tag,
        warehouse_name,
        warehouse_size,
        warehouse_type,
        cluster_number,
        start_time,
        end_time,
        execution_ms,
        bytes_scanned,
        execution_status,
        query_type,
        query_text,
        observed_at,
    ) = row
    milliseconds: int = max(0, int(execution_ms or 0))
    if _is_metadata_only_statement(query_type=query_type, query_text=query_text):
        return None, NO_WAREHOUSE_COMPUTE_REASON
    running: bool = end_time is None or str(execution_status).upper() == RUNNING_EXECUTION_STATUS
    if require_complete and running:
        return None, INCOMPLETE_HISTORY_REASON
    if milliseconds == 0 or warehouse_name is None or warehouse_size is None:
        return None, MISSING_WAREHOUSE_METADATA_REASON
    tag: dict[str, object] | None = _parse_sqlbuild_tag(query_tag)
    effective_end: datetime = observed_at if running else end_time
    active_start: datetime = max(
        start_time,
        effective_end - timedelta(milliseconds=milliseconds),
    )
    if effective_end <= active_start:
        return None, NO_WAREHOUSE_COMPUTE_REASON
    return (
        QueryCostObservation(
            query_id=str(query_id),
            warehouse_name=str(warehouse_name),
            warehouse_size=str(warehouse_size),
            warehouse_type=None if warehouse_type is None else str(warehouse_type),
            cluster_number=None if cluster_number is None else int(cluster_number),
            started_at=active_start,
            completed_at=effective_end,
            execution_ms=milliseconds,
            bytes_scanned=int(bytes_scanned or 0),
            execution_status=str(execution_status),
            run_id=None if tag is None else _optional_string(tag.get("run_id")),
            resource_type=None if tag is None else _optional_string(tag.get("resource_type")),
            resource_name=None if tag is None else _optional_string(tag.get("resource_name")),
        ),
        None,
    )


def _attribute_from_ledger(
    *,
    observation: QueryCostObservation,
    ledger: dict[str, StatementLedgerEntry],
) -> QueryCostObservation:
    entry: StatementLedgerEntry | None = ledger.get(observation.query_id)
    if entry is None:
        return replace(
            observation,
            run_id=None,
            resource_type=None,
            resource_name=None,
        )
    return replace(
        observation,
        run_id=entry.run_id,
        resource_type=entry.resource_type,
        resource_name=entry.resource_name,
    )


def _render_query_history_sql(
    *,
    database: str | None = None,
    started_at: datetime,
    completed_at: datetime,
    classification_query_ids: frozenset[str],
) -> str:
    start: str = started_at.isoformat()
    end: str = completed_at.isoformat()
    query_text_expression: str = _render_query_text_expression(
        classification_query_ids=classification_query_ids
    )
    query_history_function: str = _render_query_history_function(database=database)
    return f"""
SELECT
  QUERY_ID,
  QUERY_TAG,
  WAREHOUSE_NAME,
  WAREHOUSE_SIZE,
  WAREHOUSE_TYPE,
  CLUSTER_NUMBER,
  START_TIME,
  END_TIME,
  EXECUTION_TIME,
  BYTES_SCANNED,
  EXECUTION_STATUS,
  QUERY_TYPE,
  {query_text_expression},
  CURRENT_TIMESTAMP()
FROM TABLE({query_history_function}(
  END_TIME_RANGE_START => TO_TIMESTAMP_LTZ('{start}'),
  END_TIME_RANGE_END => TO_TIMESTAMP_LTZ('{end}'),
  RESULT_LIMIT => {_RESULT_LIMIT}
))
ORDER BY START_TIME, QUERY_ID
""".strip()


def _render_open_query_history_sql(
    *,
    database: str | None = None,
    started_at: datetime,
    classification_query_ids: frozenset[str],
) -> str:
    start: str = started_at.isoformat()
    query_text_expression: str = _render_query_text_expression(
        classification_query_ids=classification_query_ids
    )
    query_history_function: str = _render_query_history_function(database=database)
    return f"""
SELECT
  QUERY_ID,
  QUERY_TAG,
  WAREHOUSE_NAME,
  WAREHOUSE_SIZE,
  WAREHOUSE_TYPE,
  CLUSTER_NUMBER,
  START_TIME,
  END_TIME,
  EXECUTION_TIME,
  BYTES_SCANNED,
  EXECUTION_STATUS,
  QUERY_TYPE,
  {query_text_expression},
  CURRENT_TIMESTAMP()
FROM TABLE({query_history_function}(
  END_TIME_RANGE_START => TO_TIMESTAMP_LTZ('{start}'),
  RESULT_LIMIT => {_RESULT_LIMIT}
))
ORDER BY START_TIME, QUERY_ID
""".strip()


def _render_query_history_function(*, database: str | None) -> str:
    if database is None:
        return "INFORMATION_SCHEMA.QUERY_HISTORY"
    quoted_database: str = database.upper().replace('"', '""')
    return f'"{quoted_database}".INFORMATION_SCHEMA.QUERY_HISTORY'


def _render_query_text_expression(*, classification_query_ids: frozenset[str]) -> str:
    if not classification_query_ids:
        return "NULL AS QUERY_TEXT"
    query_ids: str = ", ".join(
        f"'{query_id.replace(chr(39), chr(39) * 2)}'"
        for query_id in sorted(classification_query_ids)
    )
    return (
        f"CASE WHEN QUERY_ID IN ({query_ids}) "
        "AND (QUERY_TYPE = 'CREATE' OR QUERY_TYPE LIKE 'CREATE_%') "
        "THEN QUERY_TEXT END AS QUERY_TEXT"
    )


def _parse_sqlbuild_tag(value: object) -> dict[str, object] | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        payload: object = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("app") != SQLBUILD_QUERY_TAG_APP or payload.get("v") != 1:
        return None
    return payload


def _is_metadata_only_statement(*, query_type: object, query_text: object) -> bool:
    """Identify statements Snowflake executes without warehouse compute."""

    normalized_type: str = str(query_type or "").upper().replace(" ", "_")
    if normalized_type == _USE_QUERY_TYPE or normalized_type.startswith(f"{_USE_QUERY_TYPE}_"):
        return True
    if normalized_type == _DROP_QUERY_TYPE or normalized_type.startswith(f"{_DROP_QUERY_TYPE}_"):
        return True
    if normalized_type != _CREATE_QUERY_TYPE and not normalized_type.startswith(
        f"{_CREATE_QUERY_TYPE}_"
    ):
        return False
    if not isinstance(query_text, str) or not query_text.strip():
        return False
    try:
        statement: Any = parse_one(query_text, dialect="snowflake")
    except ParseError:
        return False
    if isinstance(statement, CreateTable):
        return not any(
            (
                statement.args.get("as_select") is not None,
                statement.args.get("clone_source") is not None,
                statement.args.get("using_template") is not None,
                str(statement.args.get("table_modifier") or "").upper() == _DYNAMIC_TABLE_MODIFIER,
            )
        )
    if isinstance(statement, CreateView) and bool(statement.args.get("materialized")):
        return False
    return type(statement).__name__.startswith("Create")


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _partial_summary(*, usd_per_credit: Decimal, rate_source: str, message: str) -> RunCostSummary:
    return RunCostSummary(
        status=CostStatus.PARTIAL,
        usd_per_credit=usd_per_credit,
        rate_source=rate_source,
        message=message,
    )


def _apply_ledger_failure(*, summary: RunCostSummary, ledger_failure: str | None) -> RunCostSummary:
    if ledger_failure is None:
        return summary
    limitation: str = f"{LEDGER_PERSISTENCE_FAILURE_LIMITATION_PREFIX}{ledger_failure})."
    return replace(
        summary,
        status=CostStatus.PARTIAL,
        limitations=tuple(sorted({*summary.limitations, limitation})),
        message=summary.message or "Cost telemetry was only partially persisted.",
    )


def _apply_observation_gaps(
    *,
    summary: RunCostSummary,
    expected_statement_count: int,
    expected_query_ids: frozenset[str],
    observed_query_ids: frozenset[str],
    skipped_reasons: dict[str, str],
) -> RunCostSummary:
    relevant_skips: dict[str, str] = {
        query_id: reason
        for query_id, reason in skipped_reasons.items()
        if query_id in expected_query_ids
    }
    limitations: set[str] = set(summary.limitations)
    if MISSING_WAREHOUSE_METADATA_REASON in relevant_skips.values():
        limitations.add("One or more run statements had missing Snowflake warehouse metadata.")
    if INCOMPLETE_HISTORY_REASON in relevant_skips.values():
        limitations.add("One or more run statements were still incomplete in query history.")
    status: CostStatus = summary.status
    if MISSING_WAREHOUSE_METADATA_REASON in relevant_skips.values():
        status = CostStatus.PARTIAL
    elif INCOMPLETE_HISTORY_REASON in relevant_skips.values() and summary.query_count:
        status = CostStatus.PARTIAL
    return replace(
        summary,
        status=status,
        limitations=tuple(sorted(limitations)),
        expected_statement_count=expected_statement_count,
        observed_statement_count=len(expected_query_ids.intersection(observed_query_ids)),
        missing_statement_count=(
            expected_statement_count - len(expected_query_ids.intersection(observed_query_ids))
        ),
        skipped_statement_count=len(relevant_skips),
    )


def _has_incomplete_observation(
    *, expected_query_ids: frozenset[str], skipped_reasons: dict[str, str]
) -> bool:
    return any(
        query_id in expected_query_ids and reason in _INCOMPLETE_OBSERVATION_REASONS
        for query_id, reason in skipped_reasons.items()
    )
