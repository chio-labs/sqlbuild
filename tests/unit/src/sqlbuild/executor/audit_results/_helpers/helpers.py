"""Helpers for audit result SQL tests."""

from datetime import UTC, datetime

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.executor.audit_results.models import AuditResultRecord


def render_qualified_name(*, database: str | None, schema: str, name: str) -> str:
    del database
    return f"{schema}.{name}"


def render_framework_type(type_name: FrameworkType) -> str:
    return {
        FrameworkType.STRING: "VARCHAR",
        FrameworkType.INTEGER: "BIGINT",
        FrameworkType.TIMESTAMP: "TIMESTAMP",
    }[type_name]


def build_record(*, result_id: str, measured_value: float | None) -> AuditResultRecord:
    return AuditResultRecord(
        result_id=result_id,
        schema_version=1,
        occurred_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        invocation_id="invocation-1",
        run_id="run-1",
        audit_name="valid_orders",
        binding_key="orders.valid_orders",
        definition_fingerprint="definition-fingerprint",
        execution_fingerprint="execution-fingerprint",
        evaluation_mode="measurement",
        run_scope_phase="final",
        attachment_kind="direct",
        attached_target_kind="model",
        attached_target_name="orders",
        attached_column_name=None,
        target_database=None,
        target_schema="analytics",
        target_name="orders",
        severity="warn",
        outcome="warn",
        execution_error=None,
        violation_count=None,
        measured_value=measured_value,
        sample_count=12,
        sample_unit="rows",
        minimum_samples=10,
        thresholds_json='{"warn":{"below":99.9}}',
        evidence_json='[{"note":"it\'s invalid"}]',
        evidence_count=1,
        evidence_truncated=False,
        evidence_error=None,
        measurement_sql="SELECT AVG(is_valid) AS value FROM orders WHERE note = 'quoted'",
        evidence_sql=None,
        executed_sql="SELECT AVG(is_valid) AS value FROM orders WHERE note = 'quoted'",
        sql_digest="sql-digest",
        metadata_json=None,
        reused=False,
    )
