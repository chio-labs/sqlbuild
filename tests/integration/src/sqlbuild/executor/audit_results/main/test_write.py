"""DuckDB integration tests for append-only audit result history."""

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.audit_results.constants import AUDIT_RESULT_COLUMNS
from sqlbuild.executor.audit_results.main._write import write_audit_result_records
from sqlbuild.executor.audit_results.models import AuditResultRecord
from tests.integration.src.sqlbuild.executor.audit_results.main._test_types import (
    AuditResultWriteTestCase,
)
from tests.integration.src.sqlbuild.executor.audit_results.main.helpers import build_record


@pytest.mark.parametrize(
    "test_case",
    (
        AuditResultWriteTestCase(
            description="auto-create and append duplicate IDs",
            expected_row_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_repeated_result_records_when_writing_then_auto_creates_and_appends_both(
    test_case: AuditResultWriteTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "audit_results.duckdb")})
    record: AuditResultRecord = build_record()
    try:
        write_audit_result_records(
            connection=connection,
            execute=adapter.execute,
            database=None,
            schema="main",
            records=tuple(record for _ in range(test_case.expected_row_count)),
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_create_table_sql=adapter.render_create_audit_result_table_sql,
            render_create_index_sqls=adapter.render_create_audit_result_index_sqls,
        )
        rows: list[tuple[object, ...]] = connection.execute(
            f"SELECT {', '.join(AUDIT_RESULT_COLUMNS)} "
            "FROM main._sqlbuild_audit_results ORDER BY occurred_at"
        ).fetchall()
    finally:
        adapter.close(connection)

    # Storage is deliberately append-only: duplicate deterministic IDs remain physical rows;
    # latest-result projections own any idempotent de-duplication.
    assert len(rows) == test_case.expected_row_count
    expected: tuple[object, ...] = (
        record.result_id,
        record.schema_version,
        record.occurred_at.replace(tzinfo=None),
        record.invocation_id,
        record.run_id,
        record.audit_name,
        record.binding_key,
        record.definition_fingerprint,
        record.execution_fingerprint,
        record.evaluation_mode,
        record.run_scope_phase,
        record.attachment_kind,
        record.attached_target_kind,
        record.attached_target_name,
        record.attached_column_name,
        record.target_database,
        record.target_schema,
        record.target_name,
        record.severity,
        record.outcome,
        record.execution_error,
        record.violation_count,
        repr(record.measured_value),
        record.sample_count,
        record.sample_unit,
        record.minimum_samples,
        record.thresholds_json,
        record.evidence_json,
        record.evidence_count,
        None,
        record.evidence_error,
        record.measurement_sql,
        record.evidence_sql,
        record.executed_sql,
        record.sql_digest,
        record.metadata_json,
        "false",
    )
    assert rows == [expected] * test_case.expected_row_count
