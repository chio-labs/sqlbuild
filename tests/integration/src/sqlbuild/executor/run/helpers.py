"""Test helpers for executor run integration tests."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.fingerprints.main.create_table_sql import build_create_table_sql
from sqlbuild.compiler.fingerprints.main.write import build_insert_sql
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry, RelationReusePlan
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
    RelationReuseKind,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.reuse.fingerprint_metadata import (
    model_fingerprint_metadata_with_audit_gate,
)
from sqlbuild.executor.run.main.execute import execute_table_entry
from sqlbuild.executor.run.models import (
    HookContext,
    ModelExecutionResult,
    ModelMaterializationContext,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.integration.src.sqlbuild.executor.run._test_types import (
    TableFailureTestCase,
    TableSuccessTestCase,
)


@dataclass(frozen=True)
class ExtraAuditDefinition:
    name: str
    audit_sql: str
    severity: str


def create_python_hook_data(ctx: HookContext, value: int) -> None:
    ctx.execute_sql(
        f"CREATE TABLE {ctx.destination.schema}.python_hook_data AS SELECT {value} AS val"
    )
    ctx.log(f"python pre-hook created data for {ctx.model_name}")


def insert_table_hook_log(ctx: HookContext, phase: str) -> None:
    ctx.execute_sql(f"INSERT INTO {ctx.destination.schema}.hook_log VALUES ('{phase}')")


def fail_table_hook(ctx: HookContext, message: str) -> None:
    raise RuntimeError(message)


def build_table_plan_entry(
    *,
    name: str,
    sql: str,
    target_database: str | None = None,
    target_schema: str | None,
    target_name: str,
    type_enforcement: bool = False,
    pre_hooks: object = None,
    post_hooks: object = None,
) -> ModelPlanEntry:
    """Build a minimal ModelPlanEntry for table execution tests."""

    relation_parts: tuple[str, ...] = tuple(
        part for part in (target_database, target_schema, target_name) if part is not None
    )
    qualified: str = ".".join(relation_parts)
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.FIRST_RUN,
        destination=CompiledRelationLocation(
            database=target_database,
            schema=target_schema,
            name=target_name,
            qualified_name=qualified,
        ),
        fingerprint_query_sql=sql,
        resolved_sql=sql,
        logical_ddl=f"CREATE TABLE {qualified} AS {sql}",
        type_enforcement=type_enforcement,
        pre_hooks=pre_hooks,
        post_hooks=post_hooks,
    )


def build_reuse_table_plan_entry(
    *,
    name: str,
    sql: str,
    target_database: str | None = None,
    target_schema: str | None,
    target_name: str,
    origin_database: str | None = None,
    origin_schema: str | None,
    origin_name: str,
    hard_copy: bool,
    reuse_origin_fingerprint_database: str | None = None,
    reuse_origin_fingerprint_schema: str | None = None,
    unique_key: tuple[str, ...] = ("account_id",),
    snapshot_strategy: str = "timestamp",
    updated_at_column: str | None = "updated_at",
    check_columns: tuple[str, ...] = (),
    contract_enforced: bool = False,
    contract_columns: tuple[ColumnInfo, ...] = (),
    pre_hooks: object = None,
    post_hooks: object = None,
) -> ModelPlanEntry:
    """Build a table plan entry that reuses an origin relation."""

    origin_relation_parts: tuple[str, ...] = tuple(
        part for part in (origin_database, origin_schema, origin_name) if part is not None
    )
    origin_qualified: str = ".".join(origin_relation_parts)
    return dataclasses.replace(
        build_table_plan_entry(
            name=name,
            sql=sql,
            target_database=target_database,
            target_schema=target_schema,
            target_name=target_name,
        ),
        action=PlanAction.CREATE_TABLE,
        fingerprint_version_hash="expected_version",
        relation_reuse=RelationReusePlan(
            kind=RelationReuseKind.COMPLETE_RELATION_REUSE,
            origin=CompiledRelationLocation(
                database=origin_database,
                schema=origin_schema,
                name=origin_name,
                qualified_name=origin_qualified,
            ),
            reuse_from_target_name="prod",
            hard_copy=hard_copy,
            fingerprint_database=reuse_origin_fingerprint_database,
            fingerprint_schema=reuse_origin_fingerprint_schema or origin_schema or "",
        ),
    )


def build_reuse_snapshot_plan_entry(
    *,
    name: str,
    sql: str,
    target_database: str | None = None,
    target_schema: str | None,
    target_name: str,
    origin_database: str | None = None,
    origin_schema: str | None,
    origin_name: str,
    hard_copy: bool,
    reuse_origin_fingerprint_database: str | None = None,
    reuse_origin_fingerprint_schema: str | None = None,
    unique_key: tuple[str, ...] = ("account_id",),
    snapshot_strategy: str = "timestamp",
    updated_at_column: str | None = "updated_at",
    check_columns: tuple[str, ...] = (),
    contract_enforced: bool = False,
    contract_columns: tuple[ColumnInfo, ...] = (),
    pre_hooks: object = None,
    post_hooks: object = None,
) -> ModelPlanEntry:
    """Build a snapshot plan entry that seeds from an origin relation."""

    destination_relation_parts: tuple[str, ...] = tuple(
        part for part in (target_database, target_schema, target_name) if part is not None
    )
    origin_relation_parts: tuple[str, ...] = tuple(
        part for part in (origin_database, origin_schema, origin_name) if part is not None
    )
    destination_qualified: str = ".".join(destination_relation_parts)
    origin_qualified: str = ".".join(origin_relation_parts)
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.SNAPSHOT,
        action=PlanAction.SNAPSHOT,
        reason=PlanReason.NO_CHANGE,
        destination=CompiledRelationLocation(
            database=target_database,
            schema=target_schema,
            name=target_name,
            qualified_name=destination_qualified,
        ),
        fingerprint_query_sql=sql,
        resolved_sql=sql,
        logical_ddl="",
        unique_key=unique_key,
        snapshot_strategy=snapshot_strategy,
        updated_at_column=updated_at_column,
        check_columns=check_columns,
        contract_enforced=contract_enforced,
        contract_columns=contract_columns,
        pre_hooks=pre_hooks,
        post_hooks=post_hooks,
        fingerprint_version_hash="expected_version",
        relation_reuse=RelationReusePlan(
            kind=RelationReuseKind.SEEDED_RELATION_REUSE,
            origin=CompiledRelationLocation(
                database=origin_database,
                schema=origin_schema,
                name=origin_name,
                qualified_name=origin_qualified,
            ),
            reuse_from_target_name="prod",
            hard_copy=hard_copy,
            fingerprint_database=reuse_origin_fingerprint_database,
            fingerprint_schema=reuse_origin_fingerprint_schema or origin_schema or "",
        ),
    )


def write_matching_reuse_origin_fingerprint(
    *,
    adapter: DuckDbAdapter,
    connection: Any,
    database: str | None = None,
    schema: str,
    model_name: str,
    target_name: str,
    target_database: str | None = None,
    version_hash: str = "expected_version",
    metadata_json: str = "{}",
) -> None:
    """Create reuse origin fingerprint state matching a reuse plan entry."""

    adapter.execute(
        connection,
        sql=build_create_table_sql(
            database=database,
            schema=schema,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        ),
    )
    adapter.execute(
        connection,
        sql=build_insert_sql(
            database=database,
            schema=schema,
            fingerprint=Fingerprint(
                node_type="model",
                node_name=model_name,
                target_database=target_database,
                target_schema=schema,
                target_name=target_name,
                run_id="reuse_from_run",
                definition_hash="definition_hash",
                version_hash=version_hash,
                schema_fingerprint="schema_hash",
                definition="SELECT 1 AS id",
                metadata_json=metadata_json,
                ts=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
            ),
            render_qualified_name=adapter.render_qualified_name,
        ),
    )


def build_test_audit_plan_entry(
    *,
    name: str,
    unresolved_sql: str,
    attached_target_name: str,
    resolved_target_name: str,
    severity: str = "warn",
) -> AuditPlanEntry:
    """Build a minimal AuditPlanEntry for execution tests."""

    return AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name),
        name=name,
        resolved_sql=_resolve_audit_sql(
            unresolved_sql=unresolved_sql,
            attached_target_name=attached_target_name,
            resolved_target_name=resolved_target_name,
        ),
        unresolved_sql=unresolved_sql,
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity(severity),
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
        attached_target_name=attached_target_name,
    )


def build_test_audit_result(
    *, audit: AuditPlanEntry, outcome: AuditOutcome = AuditOutcome.PASS
) -> AuditExecutionResult:
    """Build a minimal audit execution result for fingerprint metadata tests."""

    return AuditExecutionResult(
        audit_name=audit.name,
        attachment_kind=audit.attachment_kind,
        severity=audit.severity,
        outcome=outcome,
        row_count=0 if outcome == AuditOutcome.PASS else 1,
        executed_sql=audit.resolved_sql,
        run_scope_phase=AuditRunScope.FINAL,
        attached_target_name=audit.attached_target_name,
        attached_column_name=audit.attached_column_name,
    )


def build_test_audit_gate_metadata(
    *, audit: AuditPlanEntry, outcome: AuditOutcome = AuditOutcome.PASS
) -> str:
    """Build metadata JSON containing successful audit gate proof."""

    return model_fingerprint_metadata_with_audit_gate(
        metadata_json="{}",
        model_audits=(audit,),
        audit_results=(build_test_audit_result(audit=audit, outcome=outcome),),
        run_id="reuse_from_run",
    )


def _resolve_audit_sql(
    *, unresolved_sql: str, attached_target_name: str, resolved_target_name: str
) -> str:
    return unresolved_sql.replace(f'__ref("{attached_target_name}")', resolved_target_name)


def build_declared_columns(
    columns: tuple[tuple[str, str], ...],
) -> tuple[ColumnInfo, ...]:
    """Build ColumnInfo tuple from (name, type) pairs."""

    return tuple(ColumnInfo(name=name, type=col_type) for name, col_type in columns)


def run_success_test(
    *,
    test_case: TableSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Execute a success test case and return the result."""

    result: ModelExecutionResult = _execute_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == ExecutionStatus.SUCCESS
    return result


def run_failure_test(
    *,
    test_case: TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Execute a failure test case and return the result."""

    result: ModelExecutionResult = _execute_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == ExecutionStatus.FAILED
    return result


def verify_success_warehouse_state(
    *,
    result: ModelExecutionResult,
    test_case: TableSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    """Verify warehouse state for a successful execution."""

    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    query_result: Any = connection.execute(f"SELECT * FROM {target_qualified}")
    rows: list[Any] = query_result.fetchall()
    assert len(rows) == test_case.expected_row_count
    assert len(result.audit_results) == test_case.expected_audit_count
    _verify_column_names(
        connection=connection, target_qualified=target_qualified, test_case=test_case
    )
    _verify_column_types(
        adapter=adapter,
        connection=connection,
        test_case=test_case,
    )
    _verify_warning_fragment(result=result, test_case=test_case)
    _verify_lifecycle_event_fragments(result=result, test_case=test_case)
    _verify_query_results(connection=connection, test_case=test_case)


def verify_failure_warehouse_state(
    *,
    result: ModelExecutionResult,
    test_case: TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    """Verify result fields and warehouse state for a failed execution."""

    assert result.failed_phase == test_case.expected_failed_phase
    assert len(result.audit_results) == test_case.expected_audit_count
    assert result.staging_relation == test_case.expected_staging_relation
    assert result.promoted_relation == test_case.expected_promoted_relation
    _verify_error_fragment(result=result, test_case=test_case)
    _verify_failure_row_count(connection=connection, test_case=test_case)


def _execute_test(
    *,
    test_case: TableSuccessTestCase | TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Set up and execute a table entry test case."""

    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    entry: ModelPlanEntry = build_table_plan_entry(
        name="orders",
        sql=test_case.model_sql,
        target_schema=test_case.target_schema,
        target_name=test_case.target_name,
        type_enforcement=test_case.type_enforcement,
        pre_hooks=test_case.pre_hook,
        post_hooks=test_case.post_hook,
    )

    declared_columns: tuple[ColumnInfo, ...] = build_declared_columns(test_case.declared_columns)
    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    model_audits: tuple[AuditPlanEntry, ...] = _build_model_audits(
        test_case=test_case,
        resolved_target_name=target_qualified,
    )
    model_locations: dict[str, CompiledRelationLocation] = {
        "orders": CompiledRelationLocation(
            database=None,
            schema=test_case.target_schema,
            name=test_case.target_name,
            qualified_name=target_qualified,
        ),
    }

    return execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations=model_locations,
            seed_locations={},
            source_map={},
            model_audits=model_audits,
            run_id="test_run",
            query_change_tracking=(
                test_case.query_change_tracking
                if isinstance(test_case, TableSuccessTestCase)
                else True
            ),
            hook_functions=tuple(
                hook_function
                for hook_function in getattr(test_case, "hook_functions", ())
                if isinstance(hook_function, DiscoveredHookFunction)
            ),
        ),
        declared_columns=declared_columns,
        promotion_mode=test_case.promotion_mode,
    )


def _build_model_audits(
    *, test_case: TableSuccessTestCase | TableFailureTestCase, resolved_target_name: str
) -> tuple[AuditPlanEntry, ...]:
    """Build model audits from test case audit config."""

    audits: list[AuditPlanEntry] = []
    if test_case.audit_sql is not None:
        audits.append(
            build_test_audit_plan_entry(
                name="not_null",
                unresolved_sql=test_case.audit_sql,
                attached_target_name="orders",
                resolved_target_name=resolved_target_name,
                severity=test_case.audit_severity,
            )
        )
    extra: object
    for extra in test_case.extra_audits:
        if not isinstance(extra, ExtraAuditDefinition):
            raise TypeError("extra_audits must contain ExtraAuditDefinition values")
        audits.append(
            build_test_audit_plan_entry(
                name=extra.name,
                unresolved_sql=extra.audit_sql,
                attached_target_name="orders",
                resolved_target_name=resolved_target_name,
                severity=extra.severity,
            )
        )
    return tuple(audits)


def _build_target_qualified(*, target_schema: str | None, target_name: str) -> str:
    if target_schema:
        return f"{target_schema}.{target_name}"
    return target_name


def _verify_column_names(
    *,
    connection: Any,
    target_qualified: str,
    test_case: TableSuccessTestCase,
) -> None:
    if not test_case.expected_column_names:
        return
    query_result: Any = connection.execute(f"SELECT * FROM {target_qualified} LIMIT 0")
    actual_names: tuple[str, ...] = tuple(desc[0] for desc in query_result.description)
    assert actual_names == test_case.expected_column_names


def _verify_column_types(
    *,
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: TableSuccessTestCase,
) -> None:
    if not test_case.expected_column_types:
        return
    schema: str | None = test_case.target_schema
    columns: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection, database=None, schema=schema, name=test_case.target_name
    )
    declared_names: tuple[str, ...] = tuple(col_name for col_name, _ in test_case.declared_columns)
    enforced_types: list[str] = []
    col: ColumnInfo
    for col in columns:
        if col.name.lower() in {n.lower() for n in declared_names}:
            enforced_types.append(col.type)
    assert tuple(enforced_types) == test_case.expected_column_types


def _verify_warning_fragment(
    *,
    result: ModelExecutionResult,
    test_case: TableSuccessTestCase,
) -> None:
    if test_case.expected_warning_fragment is None:
        return
    all_warnings: str = " ".join(result.warning_messages)
    assert test_case.expected_warning_fragment in all_warnings


def _verify_lifecycle_event_fragments(
    *,
    result: ModelExecutionResult,
    test_case: TableSuccessTestCase,
) -> None:
    fragment: str
    for fragment in test_case.expected_lifecycle_event_fragments:
        assert any(fragment in event.content for event in result.lifecycle_events)


def _verify_query_results(*, connection: Any, test_case: TableSuccessTestCase) -> None:
    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        actual_rows: tuple[tuple[object, ...], ...] = tuple(
            tuple(row) for row in connection.execute(query).fetchall()
        )
        assert actual_rows == expected_rows


def _verify_error_fragment(
    *,
    result: ModelExecutionResult,
    test_case: TableFailureTestCase,
) -> None:
    if test_case.expected_error_fragment is None:
        return
    assert result.error_message is not None
    assert test_case.expected_error_fragment in result.error_message


def _verify_failure_row_count(
    *,
    connection: Any,
    test_case: TableFailureTestCase,
) -> None:
    if test_case.expected_row_count is None:
        return
    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    query_result: Any = connection.execute(f"SELECT * FROM {target_qualified}")
    rows: list[Any] = query_result.fetchall()
    assert len(rows) == test_case.expected_row_count
