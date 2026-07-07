"""SQL helpers for runtime node result storage."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.executor.node_results.constants import (
    COLUMN_ERROR_MESSAGE,
    COLUMN_MATERIALIZED,
    COLUMN_METADATA_JSON_B64,
    COLUMN_NODE_NAME,
    COLUMN_NODE_TYPE,
    COLUMN_PAYLOAD_JSON_B64,
    COLUMN_RUN_ID,
    COLUMN_STATUS,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_NAME,
    COLUMN_TARGET_SCHEMA,
    COLUMN_TIMESTAMP,
    NODE_RESULTS_TABLE_NAME,
)
from sqlbuild.executor.node_results.models import NodeResultQuery, NodeResultRecord
from sqlbuild.executor.shared.exceptions import ExecutorInputError


def build_qualified_table_name(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    qualified_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=NODE_RESULTS_TABLE_NAME,
    )
    if qualified_name is None:
        raise ExecutorInputError("node result table requires a target schema")
    return qualified_name


def build_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool = False,
) -> str:
    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    string_type: str = render_framework_type(FrameworkType.STRING)
    timestamp_type: str = render_framework_type(FrameworkType.TIMESTAMP)
    table_kind: str = "TRANSIENT TABLE" if transient else "TABLE"
    return (
        f"CREATE {table_kind} IF NOT EXISTS {qualified_name} ("
        f"{COLUMN_NODE_TYPE} {string_type} NOT NULL, "
        f"{COLUMN_NODE_NAME} {string_type} NOT NULL, "
        f"{COLUMN_TARGET_DATABASE} {string_type}, "
        f"{COLUMN_TARGET_SCHEMA} {string_type}, "
        f"{COLUMN_TARGET_NAME} {string_type}, "
        f"{COLUMN_RUN_ID} {string_type} NOT NULL, "
        f"{COLUMN_STATUS} {string_type} NOT NULL, "
        f"{COLUMN_PAYLOAD_JSON_B64} {string_type} NOT NULL, "
        f"{COLUMN_METADATA_JSON_B64} {string_type} NOT NULL, "
        f"{COLUMN_ERROR_MESSAGE} {string_type}, "
        f"{COLUMN_MATERIALIZED} {string_type}, "
        f"{COLUMN_TIMESTAMP} {timestamp_type} NOT NULL"
        f")"
    )


def build_insert_sql(
    *,
    database: str | None,
    schema: str,
    record: NodeResultRecord,
    payload_json_b64: str,
    metadata_json_b64: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    return (
        f"INSERT INTO {qualified_name} ("
        f"{COLUMN_NODE_TYPE}, "
        f"{COLUMN_NODE_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_STATUS}, "
        f"{COLUMN_PAYLOAD_JSON_B64}, "
        f"{COLUMN_METADATA_JSON_B64}, "
        f"{COLUMN_ERROR_MESSAGE}, "
        f"{COLUMN_MATERIALIZED}, "
        f"{COLUMN_TIMESTAMP}"
        f") VALUES ("
        f"{_required_string_literal(record.node_type)}, "
        f"{_required_string_literal(record.node_name)}, "
        f"{_optional_string_literal(record.target_database)}, "
        f"{_optional_string_literal(record.target_schema)}, "
        f"{_optional_string_literal(record.target_name)}, "
        f"{_required_string_literal(record.run_id)}, "
        f"{_required_string_literal(record.status)}, "
        f"{_required_string_literal(payload_json_b64)}, "
        f"{_required_string_literal(metadata_json_b64)}, "
        f"{_optional_string_literal(record.error_message)}, "
        f"{_optional_string_literal(_materialized_storage(record.materialized))}, "
        f"{_required_string_literal(record.ts.isoformat())}"
        f")"
    )


def build_read_history_sql(
    *,
    database: str | None,
    schema: str,
    query: NodeResultQuery,
    render_qualified_name: Callable[..., str | None],
) -> str:
    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    predicates: list[str] = [
        f"{COLUMN_NODE_TYPE} = {_required_string_literal(query.node_type)}",
        f"{COLUMN_NODE_NAME} = {_required_string_literal(query.node_name)}",
        _optional_equality(COLUMN_TARGET_DATABASE, query.target_database),
        _optional_equality(COLUMN_TARGET_SCHEMA, query.target_schema),
        _optional_equality(COLUMN_TARGET_NAME, query.target_name),
    ]
    if query.statuses is not None:
        status_literals: str = ", ".join(
            _required_string_literal(status) for status in query.statuses
        )
        predicates.append(f"{COLUMN_STATUS} IN ({status_literals})")
    if query.run_id is not None:
        predicates.append(f"{COLUMN_RUN_ID} = {_required_string_literal(query.run_id)}")
    return (
        f"SELECT {_select_columns()} "
        f"FROM {qualified_name} "
        f"WHERE {' AND '.join(predicates)} "
        f"ORDER BY {COLUMN_TIMESTAMP} DESC, {COLUMN_RUN_ID} DESC"
    )


def _select_columns() -> str:
    return (
        f"{COLUMN_NODE_TYPE}, "
        f"{COLUMN_NODE_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_STATUS}, "
        f"{COLUMN_PAYLOAD_JSON_B64}, "
        f"{COLUMN_METADATA_JSON_B64}, "
        f"{COLUMN_ERROR_MESSAGE}, "
        f"{COLUMN_MATERIALIZED}, "
        f"{COLUMN_TIMESTAMP}"
    )


def _optional_equality(column: str, value: str | None) -> str:
    if value is None:
        return f"{column} IS NULL"
    return f"{column} = {_required_string_literal(value)}"


def _materialized_storage(value: bool | None) -> str | None:
    if value is None:
        return None
    return "true" if value else "false"


def _optional_string_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return _required_string_literal(value)


def _required_string_literal(value: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"
