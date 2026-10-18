"""DuckDB integration tests for append-only audit result history."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.audit_results.constants import (
    AUDIT_RESULT_COLUMNS,
    COLUMN_AUDIT_META_JSON,
)
from sqlbuild.executor.audit_results.main._write import write_audit_result_records
from sqlbuild.executor.audit_results.models import AuditResultColumnEvolution, AuditResultRecord
from tests.integration.src.sqlbuild.executor.audit_results.main._test_types import (
    AuditResultMetaWriteTestCase,
    AuditResultWriteTestCase,
)
from tests.integration.src.sqlbuild.executor.audit_results.main.helpers import (
    LEGACY_AUDIT_RESULT_COLUMNS,
    build_record,
    create_legacy_results_table,
    leave_results_table_absent,
)


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
        record.audit_definition_name,
        record.audit_description,
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
        None,
    )
    assert rows == [expected] * test_case.expected_row_count


@pytest.mark.parametrize(
    "test_case",
    (
        AuditResultMetaWriteTestCase(
            description="legacy table gains the meta column when meta is written",
            prepare=create_legacy_results_table,
            audit_meta_json='{"region":"emea"}',
            expected_meta_column=True,
            expected_meta=('{"region":"emea"}',),
        ),
        AuditResultMetaWriteTestCase(
            description="legacy table is left unchanged without meta",
            prepare=create_legacy_results_table,
            audit_meta_json=None,
            expected_meta_column=False,
            expected_meta=(None,),
        ),
        AuditResultMetaWriteTestCase(
            description="new table stores meta",
            prepare=leave_results_table_absent,
            audit_meta_json='{"region":"emea"}',
            expected_meta_column=True,
            expected_meta=('{"region":"emea"}',),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_results_table_generation_when_writing_meta_then_column_is_added_additively(
    test_case: AuditResultMetaWriteTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "audit_results.duckdb")})
    record: AuditResultRecord = replace(build_record(), audit_meta_json=test_case.audit_meta_json)
    try:
        test_case.prepare(adapter, connection)
        write_audit_result_records(
            connection=connection,
            execute=adapter.execute,
            database=None,
            schema="main",
            records=(record,),
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_create_table_sql=adapter.render_create_audit_result_table_sql,
            render_create_index_sqls=adapter.render_create_audit_result_index_sqls,
            column_evolution=AuditResultColumnEvolution(
                read_columns=adapter.get_columns, render_add_columns=adapter.render_add_columns
            ),
        )
        columns: tuple[str, ...] = tuple(
            column.name
            for column in adapter.get_columns(
                connection=connection, database=None, schema="main", name="_sqlbuild_audit_results"
            )
        )
        stored_meta: tuple[str | None, ...] = tuple(
            row[0]
            for row in connection.execute(
                f"SELECT json_extract_string(to_json(results), '$.{COLUMN_AUDIT_META_JSON}') "
                "FROM main._sqlbuild_audit_results AS results"
            ).fetchall()
        )
    finally:
        adapter.close(connection)

    assert (COLUMN_AUDIT_META_JSON in columns) is test_case.expected_meta_column
    assert columns[: len(LEGACY_AUDIT_RESULT_COLUMNS)] == LEGACY_AUDIT_RESULT_COLUMNS
    assert stored_meta == test_case.expected_meta


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
