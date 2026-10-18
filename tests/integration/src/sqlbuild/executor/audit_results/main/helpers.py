"""Helpers for native audit result integration tests."""

from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.audit_results.constants import AUDIT_RESULT_COLUMNS, COLUMN_AUDIT_META_JSON
from sqlbuild.executor.audit_results.models import AuditResultRecord

LEGACY_AUDIT_RESULT_COLUMNS: tuple[str, ...] = tuple(
    filter(lambda column: column != COLUMN_AUDIT_META_JSON, AUDIT_RESULT_COLUMNS)
)


def legacy_results_table_sql(adapter: DuckDbAdapter) -> str:
    """Return results-table DDL as it was before the meta column was added."""

    return adapter.render_create_audit_result_table_sql(database=None, schema="main").replace(
        f", {COLUMN_AUDIT_META_JSON} VARCHAR", ""
    )


def create_legacy_results_table(adapter: DuckDbAdapter, connection: Any) -> None:
    """Create the results table without the meta column."""

    connection.execute(legacy_results_table_sql(adapter))


def leave_results_table_absent(adapter: DuckDbAdapter, connection: Any) -> None:
    """Leave the results table for the writer to create."""

    del adapter, connection


def build_record() -> AuditResultRecord:
    return AuditResultRecord(
        result_id="deterministic-result-id",
        schema_version=1,
        occurred_at=datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC),
        invocation_id="invocation-1",
        run_id="run-1",
        audit_name="valid_orders",
        audit_definition_name="dq_column_rate",
        audit_description="Valid order percentage",
        binding_key="orders.valid_orders",
        definition_fingerprint="definition-fingerprint",
        execution_fingerprint="execution-fingerprint",
        evaluation_mode="measurement",
        run_scope_phase="final",
        attachment_kind="factory",
        attached_target_kind="model",
        attached_target_name="orders",
        attached_column_name="order_id",
        target_database=None,
        target_schema="main",
        target_name="orders_physical",
        severity="warn",
        outcome="pass",
        execution_error=None,
        violation_count=None,
        measured_value=99.5,
        sample_count=200,
        sample_unit="rows",
        minimum_samples=100,
        thresholds_json='{"warn":{"below":99}}',
        evidence_json=None,
        evidence_count=None,
        evidence_truncated=None,
        evidence_error=None,
        measurement_sql="SELECT 99.5 AS valid_rate",
        evidence_sql=None,
        executed_sql="SELECT 99.5 AS valid_rate",
        sql_digest="digest",
        metadata_json='{"owner":"data"}',
        reused=False,
    )
