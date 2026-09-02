from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.diagnostics.main.log_sql import log_sql
from sqlbuild.observability import (
    ExecutionIdentity,
    ObservabilityValidationError,
    current_execution_identity,
    execution_identity_to_dict,
    identity_scope,
    invocation_scope,
    log_stream_scope,
    operation_scope,
    resource_attempt_scope,
    run_scope,
    statement_scope,
)
from tests.unit.src.sqlbuild.runtime.observability._test_types import (
    IdentityBehaviorCase,
    IdentityFieldErrorCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityFieldErrorCase(
            description="empty invocation ID",
            field_name="invocation_id",
            field_value="",
            expected_error="invocation_id must be a non-empty string",
        ),
        IdentityFieldErrorCase(
            description="non-string invocation ID",
            field_name="invocation_id",
            field_value=1,
            expected_error="invocation_id must be a non-empty string",
        ),
        IdentityFieldErrorCase(
            description="empty run ID",
            field_name="run_id",
            field_value="",
            expected_error="run_id must be a non-empty string",
        ),
        IdentityFieldErrorCase(
            description="empty resource ID",
            field_name="resource_id",
            field_value="",
            expected_error="resource_id must be a non-empty string",
        ),
        IdentityFieldErrorCase(
            description="empty resource attempt ID",
            field_name="resource_attempt_id",
            field_value="",
            expected_error="resource_attempt_id must be a non-empty string",
        ),
        IdentityFieldErrorCase(
            description="empty operation ID",
            field_name="operation_id",
            field_value="",
            expected_error="operation_id must be a non-empty string",
        ),
        IdentityFieldErrorCase(
            description="empty statement ID",
            field_name="statement_id",
            field_value="",
            expected_error="statement_id must be a non-empty string",
        ),
        IdentityFieldErrorCase(
            description="empty log stream ID",
            field_name="log_stream_id",
            field_value="",
            expected_error="log_stream_id must be a non-empty string",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_identity_field_when_constructing_then_validation_rejects_it(
    test_case: IdentityFieldErrorCase,
) -> None:
    fields: dict[str, object] = {
        "invocation_id": "inv-explicit",
        test_case.field_name: test_case.field_value,
    }

    with pytest.raises(ObservabilityValidationError, match=test_case.expected_error):
        ExecutionIdentity(**fields)  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityBehaviorCase(
            description="explicit language-neutral IDs",
            expected_invocation_id="invocation/external",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_language_neutral_ids_when_serializing_then_values_are_preserved(
    test_case: IdentityBehaviorCase,
) -> None:
    identity: ExecutionIdentity = ExecutionIdentity(
        invocation_id="invocation/external",
        run_id="SQLBuild Run 001",
        resource_id="model:orders",
        resource_attempt_id="attempt-A",
        operation_id="operation-A",
        statement_id="statement-A",
        log_stream_id="logs-A",
    )

    serialized: dict[str, str | None] = execution_identity_to_dict(identity)

    assert serialized == {
        "invocation_id": test_case.expected_invocation_id,
        "run_id": "SQLBuild Run 001",
        "resource_id": "model:orders",
        "resource_attempt_id": "attempt-A",
        "operation_id": "operation-A",
        "statement_id": "statement-A",
        "log_stream_id": "logs-A",
    }
    with pytest.raises(FrozenInstanceError):
        identity.run_id = "replacement"  # ty: ignore[invalid-assignment]


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityBehaviorCase(
            description="nested normal scopes", expected_invocation_id="inv-explicit"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_nested_scopes_when_exiting_normally_then_each_parent_is_restored(
    test_case: IdentityBehaviorCase,
) -> None:
    assert current_execution_identity() is None

    with invocation_scope(test_case.expected_invocation_id) as invocation:
        with run_scope("Run ID Preserved") as run:
            with resource_attempt_scope(resource_id="model:orders") as resource:
                with operation_scope() as operation:
                    with statement_scope() as statement:
                        assert statement.invocation_id == test_case.expected_invocation_id
                        with log_stream_scope() as stream:
                            assert current_execution_identity() == stream
                            assert stream.log_stream_id != stream.statement_id
                            assert len(stream.log_stream_id or "") == 32
                        assert len(statement.statement_id or "") == 32
                    assert current_execution_identity() == operation
                    assert len(operation.operation_id or "") == 32
                assert current_execution_identity() == resource
                assert len(resource.resource_attempt_id or "") == 32
            assert current_execution_identity() == run
        assert current_execution_identity() == invocation
    assert current_execution_identity() is None
    with invocation_scope() as generated:
        assert len(generated.invocation_id) == 32
        int(generated.invocation_id, 16)


@pytest.mark.parametrize(
    "test_case",
    [IdentityBehaviorCase(description="exception restoration", expected_invocation_id="outer")],
    ids=lambda case: case.description,
)
def test_given_nested_scope_exception_when_unwinding_then_outer_snapshot_is_restored(
    test_case: IdentityBehaviorCase,
) -> None:
    outer: ExecutionIdentity = ExecutionIdentity(invocation_id=test_case.expected_invocation_id)

    with identity_scope(outer):
        with pytest.raises(RuntimeError, match="controlled failure"):
            with run_scope("run"):
                raise RuntimeError("controlled failure")
        assert current_execution_identity() == outer
    assert current_execution_identity() is None


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityBehaviorCase(
            description="descendant clearing from full snapshot",
            expected_invocation_id="inv-full",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fully_populated_snapshot_when_child_scopes_enter_then_descendants_clear_and_restore(
    test_case: IdentityBehaviorCase,
) -> None:
    snapshot: ExecutionIdentity = ExecutionIdentity(
        invocation_id=test_case.expected_invocation_id,
        run_id="run-old",
        resource_id="resource-old",
        resource_attempt_id="attempt-old",
        operation_id="operation-old",
        statement_id="statement-old",
        log_stream_id="stream-independent",
    )

    with identity_scope(snapshot):
        with run_scope("run-new") as run:
            assert run == ExecutionIdentity(
                invocation_id=test_case.expected_invocation_id,
                run_id="run-new",
                log_stream_id="stream-independent",
            )
        assert current_execution_identity() == snapshot
        with resource_attempt_scope(
            resource_id="resource-new", resource_attempt_id="attempt-new"
        ) as resource:
            assert resource == ExecutionIdentity(
                invocation_id=test_case.expected_invocation_id,
                run_id="run-old",
                resource_id="resource-new",
                resource_attempt_id="attempt-new",
                log_stream_id="stream-independent",
            )
        assert current_execution_identity() == snapshot
        with operation_scope("operation-new") as operation:
            assert operation == ExecutionIdentity(
                invocation_id=test_case.expected_invocation_id,
                run_id="run-old",
                resource_id="resource-old",
                resource_attempt_id="attempt-old",
                operation_id="operation-new",
                log_stream_id="stream-independent",
            )
        assert current_execution_identity() == snapshot

    assert current_execution_identity() is None


@pytest.mark.parametrize(
    "test_case",
    [IdentityBehaviorCase(description="missing optional parents", expected_invocation_id="inv")],
    ids=lambda case: case.description,
)
def test_given_missing_optional_parents_when_scoping_operation_then_they_remain_none(
    test_case: IdentityBehaviorCase,
) -> None:
    with invocation_scope(test_case.expected_invocation_id):
        with operation_scope("op") as identity:
            assert identity.invocation_id == test_case.expected_invocation_id
            assert identity.run_id is None
            assert identity.resource_id is None
            assert identity.resource_attempt_id is None
            assert identity.statement_id is None
    with run_scope("standalone run") as standalone:
        assert len(standalone.invocation_id) == 32
        assert standalone.run_id == "standalone run"
        assert standalone.resource_id is None
    assert current_execution_identity() is None


@pytest.mark.parametrize(
    "test_case",
    [IdentityBehaviorCase(description="generated retry identities", expected_invocation_id="inv")],
    ids=lambda case: case.description,
)
def test_given_retries_when_generating_child_ids_then_resource_is_stable_and_attempts_are_distinct(
    test_case: IdentityBehaviorCase,
) -> None:
    with invocation_scope(test_case.expected_invocation_id):
        with resource_attempt_scope(resource_id="resource") as first:
            with operation_scope() as first_operation:
                with statement_scope() as first_statement:
                    pass
        with resource_attempt_scope(resource_id="resource") as second:
            with operation_scope() as second_operation:
                with statement_scope() as second_statement:
                    pass

    assert first.resource_id == second.resource_id == "resource"
    assert first.invocation_id == test_case.expected_invocation_id
    assert first.resource_attempt_id != second.resource_attempt_id
    assert first_operation.operation_id != second_operation.operation_id
    assert first_statement.statement_id != second_statement.statement_id


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityBehaviorCase(
            description="copied blocking worker context", expected_invocation_id="inv"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_copied_context_when_worker_blocks_then_identity_exists_before_work_begins(
    test_case: IdentityBehaviorCase,
) -> None:
    with invocation_scope(test_case.expected_invocation_id):
        with operation_scope() as operation:
            with ThreadPoolExecutor(max_workers=1) as pool:
                observed: ExecutionIdentity | None = cast(
                    ExecutionIdentity | None,
                    pool.submit(copy_context().run, current_execution_identity).result(),
                )

    assert observed == operation
    assert operation.invocation_id == test_case.expected_invocation_id
    assert current_execution_identity() is None


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityBehaviorCase(
            description="thread propagation isolation", expected_invocation_id="inv"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_uncopied_and_copied_thread_contexts_when_workers_run_then_only_copy_propagates(
    test_case: IdentityBehaviorCase,
) -> None:
    with invocation_scope(test_case.expected_invocation_id) as identity:
        with ThreadPoolExecutor(max_workers=2) as pool:
            uncopied: ExecutionIdentity | None = pool.submit(current_execution_identity).result()
            copied: ExecutionIdentity | None = cast(
                ExecutionIdentity | None,
                pool.submit(copy_context().run, current_execution_identity).result(),
            )

    assert uncopied is None
    assert copied == identity


@pytest.mark.parametrize(
    "test_case",
    [IdentityBehaviorCase(description="async sibling isolation", expected_invocation_id="inv")],
    ids=lambda case: case.description,
)
def test_given_sibling_async_tasks_when_scoping_statements_then_identities_do_not_leak(
    test_case: IdentityBehaviorCase,
) -> None:
    async def observe(statement_id: str) -> tuple[str | None, str | None]:
        with statement_scope(statement_id) as identity:
            await asyncio.sleep(0)
            current: ExecutionIdentity | None = current_execution_identity()
            assert current is not None
            return identity.statement_id, current.statement_id

    async def run_siblings() -> tuple[tuple[str | None, str | None], ...]:
        with invocation_scope(test_case.expected_invocation_id):
            return tuple(await asyncio.gather(observe("one"), observe("two")))

    observed: tuple[tuple[str | None, str | None], ...] = asyncio.run(run_siblings())

    assert observed == (("one", "one"), ("two", "two"))
    assert current_execution_identity() is None


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityBehaviorCase(
            description="diagnostic identity correlation", expected_invocation_id="inv"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_identity_and_conflicting_context_when_logging_then_canonical_identity_wins(
    test_case: IdentityBehaviorCase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger: logging.Logger = logging.getLogger("sqlbuild.identity-test")
    caplog.set_level(logging.DEBUG, logger=logger.name)

    with invocation_scope(test_case.expected_invocation_id):
        with run_scope("run"):
            with resource_attempt_scope(resource_id="resource", resource_attempt_id="attempt"):
                with operation_scope("operation"):
                    with statement_scope("statement"):
                        with log_stream_scope("stream"):
                            with diagnostics_context(
                                sqlbuild_operation_id="ambient-operation",
                                sqlbuild_phase="execute",
                            ):
                                log_debug_event(
                                    logger=logger,
                                    message="identity",
                                    sqlbuild_operation_id="explicit-operation",
                                    sqlbuild_action_name="explicit-action",
                                )

    record: logging.LogRecord = caplog.records[-1]
    record_fields: dict[str, object] = vars(record)
    assert record_fields["sqlbuild_invocation_id"] == test_case.expected_invocation_id
    assert record_fields["sqlbuild_run_id"] == "run"
    assert record_fields["sqlbuild_resource_id"] == "resource"
    assert record_fields["sqlbuild_resource_attempt_id"] == "attempt"
    assert record_fields["sqlbuild_operation_id"] == "operation"
    assert record_fields["sqlbuild_statement_id"] == "statement"
    assert record_fields["sqlbuild_log_stream_id"] == "stream"
    assert record_fields["sqlbuild_phase"] == "execute"
    assert record_fields["sqlbuild_action_name"] == "explicit-action"


@pytest.mark.parametrize(
    "test_case",
    [
        IdentityBehaviorCase(
            description="standalone SQL canonical correlation",
            expected_invocation_id="ambient-invocation",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_standalone_run_and_conflicting_ambient_context_when_logging_sql_then_identity_wins(
    test_case: IdentityBehaviorCase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger: logging.Logger = logging.getLogger("sqlbuild.identity-sql-test")
    caplog.set_level(logging.DEBUG, logger=logger.name)

    with run_scope("SQLBuild Run / standalone") as identity:
        with diagnostics_context(
            sqlbuild_invocation_id=test_case.expected_invocation_id,
            sqlbuild_run_id="ambient-run",
            sqlbuild_operation_id="ambient-operation",
            sqlbuild_sql="ambient SQL",
            sqlbuild_phase="execute",
        ):
            log_sql(logger=logger, sql="SELECT 1", action="submit")

    record_fields: dict[str, object] = vars(caplog.records[-1])
    assert record_fields["sqlbuild_invocation_id"] == identity.invocation_id
    assert record_fields["sqlbuild_invocation_id"] != test_case.expected_invocation_id
    assert record_fields["sqlbuild_run_id"] == "SQLBuild Run / standalone"
    assert record_fields["sqlbuild_operation_id"] is None
    assert "sqlbuild_sql" not in record_fields
    assert str(record_fields["sqlbuild_sql_digest"]).startswith("sha256:")
    assert record_fields["sqlbuild_sql_action"] == "submit"
    assert record_fields["sqlbuild_phase"] == "execute"
