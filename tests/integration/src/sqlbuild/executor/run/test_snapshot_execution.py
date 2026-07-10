"""Integration tests for snapshot run execution."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.executor.run.main.execute import execute_snapshot_entry
from sqlbuild.executor.run.models import ModelExecutionResult, ModelMaterializationContext
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.shared.models import SqlHookEntry
from tests.integration.src.sqlbuild.executor.run._test_types import (
    SnapshotReuseExecutionTestCase,
    SnapshotReuseFailureExecutionTestCase,
    SnapshotReuseVariantExecutionTestCase,
)
from tests.integration.src.sqlbuild.executor.run.helpers import (
    build_reuse_snapshot_plan_entry,
    build_test_audit_gate_metadata,
    build_test_audit_plan_entry,
    write_matching_reuse_origin_fingerprint,
)


class ZeroCopyDuckDbAdapter(DuckDbAdapter):
    """DuckDB test adapter that exercises the cheap-reuse executor path."""

    adapter_name: ClassVar[str] = "duckdb_zero_copy_snapshot_test"

    def supports_zero_copy_clone(self) -> bool:
        return True


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseExecutionTestCase(
            description="snapshot seed reuse promotes seed and catches up",
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
                (1, "pro", "2024-01-03 00:00:00", None),
                (2, "basic", "2024-01-02 00:00:00", None),
            ),
            expected_lifecycle_fragments=(
                "account_snapshot__reuse_seed",
                "ALTER TABLE dev.account_snapshot__reuse_seed",
            ),
            expected_seed_exists=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_seed_reuse_when_running_snapshot_then_promotes_seed_and_catches_up(
    test_case: SnapshotReuseExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="CREATE SCHEMA prod")
        adapter.execute(connection, sql="CREATE SCHEMA dev")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod.account_snapshot AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.raw_accounts AS "
            "SELECT 1 AS account_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at "
            "UNION ALL SELECT 2 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            schema="prod",
            model_name="account_snapshot",
            target_name="account_snapshot",
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan, updated_at FROM dev.raw_accounts",
            target_schema="dev",
            target_name="account_snapshot",
            origin_schema="prod",
            origin_name="account_snapshot",
            hard_copy=True,
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={},
                seed_locations={},
                source_map={},
                model_audits=(),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row)
            for row in adapter.execute(
                connection,
                sql="SELECT account_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
                "FROM dev.account_snapshot ORDER BY account_id, valid_from",
            ).fetchall()
        )
        seed_exists: bool = adapter.relation_exists(
            connection,
            database=None,
            schema="dev",
            name="account_snapshot__reuse_seed",
        )

        assert result.status.value == test_case.expected_status
        assert rows == test_case.expected_rows
        assert seed_exists is test_case.expected_seed_exists
        executed_sql: tuple[str, ...] = tuple(event.content for event in result.lifecycle_events)
        expected_fragment: str
        for expected_fragment in test_case.expected_lifecycle_fragments:
            assert any(expected_fragment in sql for sql in executed_sql)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseFailureExecutionTestCase(
            description="snapshot seed reuse rejects fingerprint mismatch",
            fingerprint_version_hash="stale_version",
            expected_status=ExecutionStatus.FAILED.value,
            expected_error_fragment="reuse origin fingerprint changed after planning",
            expected_target_exists=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_seed_reuse_fingerprint_mismatch_when_running_snapshot_then_fails(
    test_case: SnapshotReuseFailureExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="CREATE SCHEMA prod")
        adapter.execute(connection, sql="CREATE SCHEMA dev")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod.account_snapshot AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.raw_accounts AS "
            "SELECT 1 AS account_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            schema="prod",
            model_name="account_snapshot",
            target_name="account_snapshot",
            version_hash=test_case.fingerprint_version_hash,
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan, updated_at FROM dev.raw_accounts",
            target_schema="dev",
            target_name="account_snapshot",
            origin_schema="prod",
            origin_name="account_snapshot",
            hard_copy=True,
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={},
                seed_locations={},
                source_map={},
                model_audits=(),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        target_exists: bool = adapter.relation_exists(
            connection,
            database=None,
            schema="dev",
            name="account_snapshot",
        )

        assert result.status.value == test_case.expected_status
        assert result.error_message is not None
        assert test_case.expected_error_fragment in result.error_message
        assert target_exists is test_case.expected_target_exists
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseVariantExecutionTestCase(
            description="cheap snapshot seed reuse materializes from origin",
            reuse_hard_copy=False,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((1, "basic"),),
            expected_lifecycle_fragments=(
                "CREATE OR REPLACE TABLE dev.account_snapshot__reuse_seed AS SELECT * "
                "FROM prod.account_snapshot",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cheap_snapshot_seed_reuse_when_running_snapshot_then_materializes_from_origin(
    test_case: SnapshotReuseVariantExecutionTestCase,
) -> None:
    adapter: ZeroCopyDuckDbAdapter = ZeroCopyDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="CREATE SCHEMA prod")
        adapter.execute(connection, sql="CREATE SCHEMA dev")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod.account_snapshot AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.raw_accounts AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            schema="prod",
            model_name="account_snapshot",
            target_name="account_snapshot",
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan, updated_at FROM dev.raw_accounts",
            target_schema="dev",
            target_name="account_snapshot",
            origin_schema="prod",
            origin_name="account_snapshot",
            hard_copy=test_case.reuse_hard_copy,
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={},
                seed_locations={},
                source_map={},
                model_audits=(),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row)
            for row in adapter.execute(
                connection,
                sql="SELECT account_id, plan FROM dev.account_snapshot ORDER BY account_id",
            ).fetchall()
        )
        lifecycle_sql: tuple[str, ...] = tuple(event.content for event in result.lifecycle_events)

        assert result.status.value == test_case.expected_status
        assert rows == test_case.expected_rows
        expected_fragment: str
        for expected_fragment in test_case.expected_lifecycle_fragments:
            assert any(expected_fragment in statement for statement in lifecycle_sql)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseVariantExecutionTestCase(
            description=(
                "existing snapshot destination is replaced by promoted seed then catches up"
            ),
            reuse_hard_copy=True,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
                (1, "pro", "2024-01-03 00:00:00", None),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_snapshot_destination_when_running_seed_reuse_then_promotes_seed(
    test_case: SnapshotReuseVariantExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="CREATE SCHEMA prod")
        adapter.execute(connection, sql="CREATE SCHEMA dev")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod.account_snapshot AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.account_snapshot AS "
            "SELECT 99 AS account_id, 'stale-dev' AS plan, "
            "TIMESTAMP '2023-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2023-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.raw_accounts AS "
            "SELECT 1 AS account_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            schema="prod",
            model_name="account_snapshot",
            target_name="account_snapshot",
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan, updated_at FROM dev.raw_accounts",
            target_schema="dev",
            target_name="account_snapshot",
            origin_schema="prod",
            origin_name="account_snapshot",
            hard_copy=test_case.reuse_hard_copy,
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={},
                seed_locations={},
                source_map={},
                model_audits=(),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row)
            for row in adapter.execute(
                connection,
                sql="SELECT account_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
                "FROM dev.account_snapshot ORDER BY account_id, valid_from",
            ).fetchall()
        )

        assert result.status.value == test_case.expected_status
        assert rows == test_case.expected_rows
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseFailureExecutionTestCase(
            description="fingerprint mismatch leaves existing snapshot destination unchanged",
            fingerprint_version_hash="stale_version",
            expected_status=ExecutionStatus.FAILED.value,
            expected_error_fragment="reuse origin fingerprint changed after planning",
            expected_target_exists=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_snapshot_destination_when_seed_reuse_fails_then_destination_is_unchanged(
    test_case: SnapshotReuseFailureExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="CREATE SCHEMA prod")
        adapter.execute(connection, sql="CREATE SCHEMA dev")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod.account_snapshot AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.account_snapshot AS "
            "SELECT 99 AS account_id, 'keep-dev' AS plan, "
            "TIMESTAMP '2023-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2023-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.raw_accounts AS "
            "SELECT 1 AS account_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            schema="prod",
            model_name="account_snapshot",
            target_name="account_snapshot",
            version_hash=test_case.fingerprint_version_hash,
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan, updated_at FROM dev.raw_accounts",
            target_schema="dev",
            target_name="account_snapshot",
            origin_schema="prod",
            origin_name="account_snapshot",
            hard_copy=True,
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={},
                seed_locations={},
                source_map={},
                model_audits=(),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row)
            for row in adapter.execute(
                connection,
                sql="SELECT account_id, plan FROM dev.account_snapshot ORDER BY account_id",
            ).fetchall()
        )
        target_exists: bool = adapter.relation_exists(
            connection,
            database=None,
            schema="dev",
            name="account_snapshot",
        )

        assert result.status.value == test_case.expected_status
        assert result.error_message is not None
        assert test_case.expected_error_fragment in result.error_message
        assert target_exists is test_case.expected_target_exists
        assert rows == ((99, "keep-dev"),)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseVariantExecutionTestCase(
            description="check snapshot seed reuse tracks checked column change",
            reuse_hard_copy=True,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((1, "basic", False), (1, "pro", True)),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_check_snapshot_seed_reuse_when_running_snapshot_then_tracks_checked_change(
    test_case: SnapshotReuseVariantExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="CREATE SCHEMA prod")
        adapter.execute(connection, sql="CREATE SCHEMA dev")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod.account_snapshot AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.raw_accounts AS SELECT 1 AS account_id, 'pro' AS plan",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            schema="prod",
            model_name="account_snapshot",
            target_name="account_snapshot",
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan FROM dev.raw_accounts",
            target_schema="dev",
            target_name="account_snapshot",
            origin_schema="prod",
            origin_name="account_snapshot",
            hard_copy=test_case.reuse_hard_copy,
            snapshot_strategy="check",
            updated_at_column=None,
            check_columns=("plan",),
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={},
                seed_locations={},
                source_map={},
                model_audits=(),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row)
            for row in adapter.execute(
                connection,
                sql="SELECT account_id, plan, valid_to IS NULL FROM dev.account_snapshot "
                "ORDER BY account_id, plan",
            ).fetchall()
        )

        assert result.status.value == test_case.expected_status
        assert rows == test_case.expected_rows
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseVariantExecutionTestCase(
            description="snapshot seed reuse still runs hooks audits and contracts",
            reuse_hard_copy=True,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=(("post",), ("pre",)),
            expected_audit_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_seed_reuse_with_hooks_audits_and_contract_when_running_then_succeeds(
    test_case: SnapshotReuseVariantExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="CREATE SCHEMA prod")
        adapter.execute(connection, sql="CREATE SCHEMA dev")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod.account_snapshot AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.raw_accounts AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            schema="prod",
            model_name="account_snapshot",
            target_name="account_snapshot",
        )
        audit: AuditPlanEntry = build_test_audit_plan_entry(
            name="account_snapshot_not_null",
            unresolved_sql=(
                'SELECT account_id FROM __ref("account_snapshot") WHERE account_id IS NULL'
            ),
            attached_target_name="account_snapshot",
            resolved_target_name="dev.account_snapshot",
        )
        audit = AuditPlanEntry(
            key=audit.key,
            name=audit.name,
            resolved_sql=audit.resolved_sql,
            unresolved_sql=audit.unresolved_sql,
            attachment_kind=audit.attachment_kind,
            severity=audit.severity,
            requested_run_scope=AuditRunScope.FINAL,
            effective_run_scope=AuditRunScope.FINAL,
            attached_target_name=audit.attached_target_name,
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan, updated_at FROM dev.raw_accounts",
            target_schema="dev",
            target_name="account_snapshot",
            origin_schema="prod",
            origin_name="account_snapshot",
            hard_copy=test_case.reuse_hard_copy,
            contract_enforced=True,
            contract_columns=(
                ColumnInfo(name="account_id", type="INTEGER"),
                ColumnInfo(name="plan", type="VARCHAR"),
                ColumnInfo(name="updated_at", type="TIMESTAMP"),
            ),
            pre_hooks=SqlHookEntry(
                statement="CREATE TABLE dev.snapshot_hook_log AS SELECT 'pre' AS phase"
            ),
            post_hooks=SqlHookEntry(statement="INSERT INTO dev.snapshot_hook_log VALUES ('post')"),
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={"account_snapshot": entry.destination},
                seed_locations={},
                source_map={},
                model_audits=(audit,),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        hook_rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row)
            for row in adapter.execute(
                connection, sql="SELECT phase FROM dev.snapshot_hook_log ORDER BY phase"
            ).fetchall()
        )

        assert result.status.value == test_case.expected_status
        assert len(result.audit_results) == test_case.expected_audit_count
        assert hook_rows == test_case.expected_rows
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseVariantExecutionTestCase(
            description="snapshot seed reuse appends new source column during normal snapshot flow",
            reuse_hard_copy=True,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((1, "gold"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_seed_reuse_with_schema_change_when_running_then_appends_column(
    test_case: SnapshotReuseVariantExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="CREATE SCHEMA prod")
        adapter.execute(connection, sql="CREATE SCHEMA dev")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod.account_snapshot AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.raw_accounts AS "
            "SELECT 1 AS account_id, 'basic' AS plan, 'gold' AS tier, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            schema="prod",
            model_name="account_snapshot",
            target_name="account_snapshot",
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan, tier, updated_at FROM dev.raw_accounts",
            target_schema="dev",
            target_name="account_snapshot",
            origin_schema="prod",
            origin_name="account_snapshot",
            hard_copy=test_case.reuse_hard_copy,
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={},
                seed_locations={},
                source_map={},
                model_audits=(),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row)
            for row in adapter.execute(
                connection,
                sql="SELECT account_id, tier FROM dev.account_snapshot WHERE valid_to IS NULL",
            ).fetchall()
        )

        assert result.status.value == test_case.expected_status
        assert rows == test_case.expected_rows
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseVariantExecutionTestCase(
            description="snapshot seed reuse executes audits despite accepted origin proof",
            reuse_hard_copy=True,
            expected_status=ExecutionStatus.FAILED.value,
            expected_rows=(),
            expected_audit_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_seed_reuse_with_origin_audit_proof_when_running_then_audit_still_executes(
    test_case: SnapshotReuseVariantExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="CREATE SCHEMA prod")
        adapter.execute(connection, sql="CREATE SCHEMA dev")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod.account_snapshot AS "
            "SELECT NULL::INTEGER AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev.raw_accounts AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at WHERE 1 = 0",
        )
        origin_audit: AuditPlanEntry = build_test_audit_plan_entry(
            name="account_snapshot_not_null",
            unresolved_sql=(
                'SELECT account_id FROM __ref("account_snapshot") WHERE account_id IS NULL'
            ),
            attached_target_name="account_snapshot",
            resolved_target_name="prod.account_snapshot",
            severity="error",
        )
        planned_audit: AuditPlanEntry = build_test_audit_plan_entry(
            name="account_snapshot_not_null",
            unresolved_sql=(
                'SELECT account_id FROM __ref("account_snapshot") WHERE account_id IS NULL'
            ),
            attached_target_name="account_snapshot",
            resolved_target_name="dev.account_snapshot",
            severity="error",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            schema="prod",
            model_name="account_snapshot",
            target_name="account_snapshot",
            metadata_json=build_test_audit_gate_metadata(audit=origin_audit),
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan, updated_at FROM dev.raw_accounts",
            target_schema="dev",
            target_name="account_snapshot",
            origin_schema="prod",
            origin_name="account_snapshot",
            hard_copy=test_case.reuse_hard_copy,
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={"account_snapshot": entry.destination},
                seed_locations={},
                source_map={},
                model_audits=(planned_audit,),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        assert result.status.value == test_case.expected_status
        assert result.failed_phase == ExecutionPhase.AUDIT
        assert len(result.audit_results) == test_case.expected_audit_count
        assert result.audit_results[0].reused is False
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReuseVariantExecutionTestCase(
            description="database-qualified snapshot reuse origin materializes destination",
            reuse_hard_copy=True,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((1, "basic"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_database_qualified_snapshot_reuse_origin_when_running_then_materializes_destination(
    test_case: SnapshotReuseVariantExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, sql="ATTACH ':memory:' AS prod_db")
        adapter.execute(connection, sql="ATTACH ':memory:' AS dev_db")
        adapter.execute(connection, sql="CREATE SCHEMA prod_db.staging")
        adapter.execute(connection, sql="CREATE SCHEMA dev_db.staging")
        adapter.execute(
            connection,
            sql="CREATE TABLE prod_db.staging.account_snapshot AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at, "
            "TIMESTAMP '2024-01-01 00:00:00' AS valid_from, NULL::TIMESTAMP AS valid_to",
        )
        adapter.execute(
            connection,
            sql="CREATE TABLE dev_db.staging.raw_accounts AS "
            "SELECT 1 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        )
        write_matching_reuse_origin_fingerprint(
            adapter=adapter,
            connection=connection,
            database="prod_db",
            schema="staging",
            model_name="account_snapshot",
            target_database="prod_db",
            target_name="account_snapshot",
        )
        entry: ModelPlanEntry = build_reuse_snapshot_plan_entry(
            name="account_snapshot",
            sql="SELECT account_id, plan, updated_at FROM dev_db.staging.raw_accounts",
            target_database="dev_db",
            target_schema="staging",
            target_name="account_snapshot",
            origin_database="prod_db",
            origin_schema="staging",
            origin_name="account_snapshot",
            hard_copy=test_case.reuse_hard_copy,
            reuse_origin_fingerprint_database="prod_db",
            reuse_origin_fingerprint_schema="staging",
        )

        result: ModelExecutionResult = execute_snapshot_entry(
            context=ModelMaterializationContext(
                entry=entry,
                adapter=adapter,
                connection=connection,
                model_locations={},
                seed_locations={},
                source_map={},
                model_audits=(),
                run_id="test_run",
                query_change_tracking=False,
            ),
        )

        rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row)
            for row in adapter.execute(
                connection,
                sql="SELECT account_id, plan FROM dev_db.staging.account_snapshot ORDER BY account_id",
            ).fetchall()
        )

        assert result.status.value == test_case.expected_status
        assert rows == test_case.expected_rows
    finally:
        adapter.close(connection)
