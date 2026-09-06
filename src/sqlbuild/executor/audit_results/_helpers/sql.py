"""Portable SQL builders for append-only audit result history."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.audit_results.constants import (
    AUDIT_RESULT_COLUMN_TYPES,
    AUDIT_RESULT_COLUMNS,
    AUDIT_RESULTS_TABLE_NAME,
    COLUMN_ATTACHED_COLUMN_NAME,
    COLUMN_ATTACHED_TARGET_KIND,
    COLUMN_ATTACHED_TARGET_NAME,
    COLUMN_ATTACHMENT_KIND,
    COLUMN_AUDIT_DEFINITION_NAME,
    COLUMN_AUDIT_DESCRIPTION,
    COLUMN_AUDIT_NAME,
    COLUMN_BINDING_KEY,
    COLUMN_DEFINITION_FINGERPRINT,
    COLUMN_EVALUATION_MODE,
    COLUMN_EVIDENCE_COUNT,
    COLUMN_EVIDENCE_ERROR,
    COLUMN_EVIDENCE_JSON,
    COLUMN_EVIDENCE_SQL,
    COLUMN_EVIDENCE_TRUNCATED,
    COLUMN_EXECUTED_SQL,
    COLUMN_EXECUTION_ERROR,
    COLUMN_EXECUTION_FINGERPRINT,
    COLUMN_INVOCATION_ID,
    COLUMN_MEASURED_VALUE,
    COLUMN_MEASUREMENT_SQL,
    COLUMN_METADATA_JSON,
    COLUMN_MINIMUM_SAMPLES,
    COLUMN_OCCURRED_AT,
    COLUMN_OUTCOME,
    COLUMN_RESULT_ID,
    COLUMN_REUSED,
    COLUMN_RUN_ID,
    COLUMN_RUN_SCOPE_PHASE,
    COLUMN_SAMPLE_COUNT,
    COLUMN_SAMPLE_UNIT,
    COLUMN_SCHEMA_VERSION,
    COLUMN_SEVERITY,
    COLUMN_SQL_DIGEST,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_NAME,
    COLUMN_TARGET_SCHEMA,
    COLUMN_THRESHOLDS_JSON,
    COLUMN_VIOLATION_COUNT,
)
from sqlbuild.executor.audit_results.models import AuditResultRecord
from sqlbuild.sql_values.main.render_state_literal import render_state_sql_literal
from sqlbuild.sql_values.types import StateSqlValueType

_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        COLUMN_RESULT_ID,
        COLUMN_SCHEMA_VERSION,
        COLUMN_OCCURRED_AT,
        COLUMN_INVOCATION_ID,
        COLUMN_RUN_ID,
        COLUMN_AUDIT_NAME,
        COLUMN_AUDIT_DEFINITION_NAME,
        COLUMN_BINDING_KEY,
        COLUMN_DEFINITION_FINGERPRINT,
        COLUMN_EXECUTION_FINGERPRINT,
        COLUMN_EVALUATION_MODE,
        COLUMN_RUN_SCOPE_PHASE,
        COLUMN_ATTACHMENT_KIND,
        COLUMN_SEVERITY,
        COLUMN_OUTCOME,
        COLUMN_REUSED,
    }
)


def build_qualified_table_name(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    qualified_name: str | None = render_qualified_name(
        database=database, schema=schema, name=AUDIT_RESULTS_TABLE_NAME
    )
    if qualified_name is None:
        raise ExecutorInputError("audit result table requires a target schema")
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
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    rendered_types: dict[StateSqlValueType, str] = {
        StateSqlValueType.STRING: render_framework_type(FrameworkType.STRING),
        StateSqlValueType.INTEGER: render_framework_type(FrameworkType.INTEGER),
        StateSqlValueType.TEXT_TIMESTAMP: render_framework_type(FrameworkType.TIMESTAMP),
    }
    definitions: list[str] = []
    for column in AUDIT_RESULT_COLUMNS:
        required: str = " NOT NULL" if column in _REQUIRED_COLUMNS else ""
        column_type: str = rendered_types[AUDIT_RESULT_COLUMN_TYPES[column]]
        definitions.append(f"{column} {column_type}{required}")
    table_kind: str = "TRANSIENT TABLE" if transient else "TABLE"
    return f"CREATE {table_kind} IF NOT EXISTS {qualified_name} ({', '.join(definitions)})"


def build_insert_sql(
    *,
    database: str | None,
    schema: str,
    records: Sequence[AuditResultRecord],
    render_qualified_name: Callable[..., str | None],
) -> str:
    if not records:
        raise ExecutorInputError("audit result insert requires at least one record")
    qualified_name: str = build_qualified_table_name(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    rows: str = ", ".join(_record_values(record) for record in records)
    return f"INSERT INTO {qualified_name} ({', '.join(AUDIT_RESULT_COLUMNS)}) VALUES {rows}"


def build_read_latest_sql(
    *,
    database: str | None,
    schema: str,
    audit_name: str,
    binding_key: str,
    execution_fingerprint: str,
    run_scope_phase: str,
    limit: int,
    render_qualified_name: Callable[..., str | None],
) -> str:
    qualified_name: str = build_qualified_table_name(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    predicates: tuple[tuple[str, str], ...] = (
        (COLUMN_AUDIT_NAME, audit_name),
        (COLUMN_BINDING_KEY, binding_key),
        (COLUMN_EXECUTION_FINGERPRINT, execution_fingerprint),
        (COLUMN_RUN_SCOPE_PHASE, run_scope_phase),
    )
    where_sql: str = " AND ".join(
        f"{column} = {_column_literal(column=column, value=value)}" for column, value in predicates
    )
    return (
        f"SELECT {', '.join(AUDIT_RESULT_COLUMNS)} FROM {qualified_name} "
        f"WHERE {where_sql} ORDER BY {COLUMN_OCCURRED_AT} DESC, {COLUMN_RESULT_ID} DESC "
        f"LIMIT {limit}"
    )


def _record_values(record: AuditResultRecord) -> str:
    values: dict[str, object | None] = {
        COLUMN_RESULT_ID: record.result_id,
        COLUMN_SCHEMA_VERSION: record.schema_version,
        COLUMN_OCCURRED_AT: record.occurred_at,
        COLUMN_INVOCATION_ID: record.invocation_id,
        COLUMN_RUN_ID: record.run_id,
        COLUMN_AUDIT_NAME: record.audit_name,
        COLUMN_AUDIT_DEFINITION_NAME: record.audit_definition_name,
        COLUMN_AUDIT_DESCRIPTION: record.audit_description,
        COLUMN_BINDING_KEY: record.binding_key,
        COLUMN_DEFINITION_FINGERPRINT: record.definition_fingerprint,
        COLUMN_EXECUTION_FINGERPRINT: record.execution_fingerprint,
        COLUMN_EVALUATION_MODE: record.evaluation_mode,
        COLUMN_RUN_SCOPE_PHASE: record.run_scope_phase,
        COLUMN_ATTACHMENT_KIND: record.attachment_kind,
        COLUMN_ATTACHED_TARGET_KIND: record.attached_target_kind,
        COLUMN_ATTACHED_TARGET_NAME: record.attached_target_name,
        COLUMN_ATTACHED_COLUMN_NAME: record.attached_column_name,
        COLUMN_TARGET_DATABASE: record.target_database,
        COLUMN_TARGET_SCHEMA: record.target_schema,
        COLUMN_TARGET_NAME: record.target_name,
        COLUMN_SEVERITY: record.severity,
        COLUMN_OUTCOME: record.outcome,
        COLUMN_EXECUTION_ERROR: record.execution_error,
        COLUMN_VIOLATION_COUNT: record.violation_count,
        COLUMN_MEASURED_VALUE: _canonical_float(record.measured_value),
        COLUMN_SAMPLE_COUNT: record.sample_count,
        COLUMN_SAMPLE_UNIT: record.sample_unit,
        COLUMN_MINIMUM_SAMPLES: record.minimum_samples,
        COLUMN_THRESHOLDS_JSON: record.thresholds_json,
        COLUMN_EVIDENCE_JSON: record.evidence_json,
        COLUMN_EVIDENCE_COUNT: record.evidence_count,
        COLUMN_EVIDENCE_TRUNCATED: _text_boolean(record.evidence_truncated),
        COLUMN_EVIDENCE_ERROR: record.evidence_error,
        COLUMN_MEASUREMENT_SQL: record.measurement_sql,
        COLUMN_EVIDENCE_SQL: record.evidence_sql,
        COLUMN_EXECUTED_SQL: record.executed_sql,
        COLUMN_SQL_DIGEST: record.sql_digest,
        COLUMN_METADATA_JSON: record.metadata_json,
        COLUMN_REUSED: _text_boolean(record.reused),
    }
    return (
        "("
        + ", ".join(
            _column_literal(column=column, value=values[column]) for column in AUDIT_RESULT_COLUMNS
        )
        + ")"
    )


def _canonical_float(value: float | None) -> str | None:
    return None if value is None else repr(value)


def _text_boolean(value: bool | None) -> str | None:
    if value is None:
        return None
    return "true" if value else "false"


def _column_literal(*, column: str, value: object | None) -> str:
    return render_state_sql_literal(value=value, declared_type=AUDIT_RESULT_COLUMN_TYPES[column])
