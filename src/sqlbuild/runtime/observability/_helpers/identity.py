"""Execution identity context primitives."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, replace
from types import MappingProxyType
from typing import cast
from uuid import uuid4

from sqlbuild.runtime.observability._helpers.validation import freeze_json
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import ExecutionIdentity
from sqlbuild.runtime.observability.types import JSONValue

_CURRENT_EXECUTION_IDENTITY: ContextVar[ExecutionIdentity | None] = ContextVar(
    "sqlbuild_execution_identity", default=None
)


_CURRENT_INVOCATION_EXTERNAL_CONTEXT: ContextVar[Mapping[str, JSONValue]] = ContextVar(
    "sqlbuild_invocation_external_context", default=MappingProxyType({})
)


def current_execution_identity() -> ExecutionIdentity | None:
    return _CURRENT_EXECUTION_IDENTITY.get()


@contextmanager
def identity_scope(identity: ExecutionIdentity) -> Iterator[ExecutionIdentity]:
    identity_token: Token[ExecutionIdentity | None] = _CURRENT_EXECUTION_IDENTITY.set(identity)
    try:
        yield identity
    finally:
        _CURRENT_EXECUTION_IDENTITY.reset(identity_token)


def execution_identity_to_dict(identity: ExecutionIdentity) -> dict[str, str | None]:
    return asdict(identity)


def _required_current_identity() -> ExecutionIdentity:
    current: ExecutionIdentity | None = current_execution_identity()
    if current is None:
        raise ObservabilityValidationError("an invocation identity must be active")
    return current


@contextmanager
def invocation_scope(invocation_id: str | None = None) -> Iterator[ExecutionIdentity]:
    identity: ExecutionIdentity = ExecutionIdentity(
        invocation_id=uuid4().hex if invocation_id is None else invocation_id
    )
    with identity_scope(identity) as installed:
        yield installed


def current_invocation_external_context() -> Mapping[str, JSONValue]:
    """Return validated external context for the active invocation."""

    return _CURRENT_INVOCATION_EXTERNAL_CONTEXT.get()


@contextmanager
def invocation_external_context_scope(
    *, external_context: Mapping[str, object]
) -> Iterator[Mapping[str, JSONValue]]:
    """Install validated integration context for lifecycle facts in one command."""

    frozen: JSONValue = freeze_json(value=external_context, path="external_context")
    if not isinstance(frozen, Mapping):
        raise ObservabilityValidationError("external_context must be a JSON object")
    context: Mapping[str, JSONValue] = cast(Mapping[str, JSONValue], frozen)
    token: Token[Mapping[str, JSONValue]] = _CURRENT_INVOCATION_EXTERNAL_CONTEXT.set(context)
    try:
        yield context
    finally:
        _CURRENT_INVOCATION_EXTERNAL_CONTEXT.reset(token)


@contextmanager
def run_scope(run_id: str) -> Iterator[ExecutionIdentity]:
    current: ExecutionIdentity | None = current_execution_identity()
    parent: ExecutionIdentity = (
        ExecutionIdentity(invocation_id=uuid4().hex) if current is None else current
    )
    identity: ExecutionIdentity = replace(
        parent,
        run_id=run_id,
        resource_id=None,
        resource_attempt_id=None,
        operation_id=None,
        statement_id=None,
    )
    with identity_scope(identity) as installed:
        yield installed


@contextmanager
def resource_attempt_scope(
    *, resource_id: str, resource_attempt_id: str | None = None
) -> Iterator[ExecutionIdentity]:
    identity: ExecutionIdentity = replace(
        _required_current_identity(),
        resource_id=resource_id,
        resource_attempt_id=(uuid4().hex if resource_attempt_id is None else resource_attempt_id),
        operation_id=None,
        statement_id=None,
    )
    with identity_scope(identity) as installed:
        yield installed


@contextmanager
def operation_scope(operation_id: str | None = None) -> Iterator[ExecutionIdentity]:
    identity: ExecutionIdentity = replace(
        _required_current_identity(),
        operation_id=uuid4().hex if operation_id is None else operation_id,
        statement_id=None,
    )
    with identity_scope(identity) as installed:
        yield installed


@contextmanager
def statement_scope(statement_id: str | None = None) -> Iterator[ExecutionIdentity]:
    identity: ExecutionIdentity = replace(
        _required_current_identity(),
        statement_id=uuid4().hex if statement_id is None else statement_id,
    )
    with identity_scope(identity) as installed:
        yield installed


@contextmanager
def log_stream_scope(log_stream_id: str | None = None) -> Iterator[ExecutionIdentity]:
    identity: ExecutionIdentity = replace(
        _required_current_identity(),
        log_stream_id=uuid4().hex if log_stream_id is None else log_stream_id,
    )
    with identity_scope(identity) as installed:
        yield installed
