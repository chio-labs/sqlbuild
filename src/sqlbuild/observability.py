"""Public runtime observability API."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.main.current_execution_identity import (
    current_execution_identity as _current_execution_identity,
)
from sqlbuild.runtime.observability.main.diagnostic_log_from_json import (
    diagnostic_log_from_json as _diagnostic_log_from_json,
)
from sqlbuild.runtime.observability.main.diagnostic_log_to_json import (
    diagnostic_log_to_json as _diagnostic_log_to_json,
)
from sqlbuild.runtime.observability.main.execution_identity_to_dict import (
    execution_identity_to_dict as _execution_identity_to_dict,
)
from sqlbuild.runtime.observability.main.identity_scope import identity_scope as _identity_scope
from sqlbuild.runtime.observability.main.invocation_scope import (
    invocation_scope as _invocation_scope,
)
from sqlbuild.runtime.observability.main.is_terminal_event import (
    is_terminal_event as _is_terminal_event,
)
from sqlbuild.runtime.observability.main.lifecycle_event_from_json import (
    lifecycle_event_from_json as _lifecycle_event_from_json,
)
from sqlbuild.runtime.observability.main.lifecycle_event_to_json import (
    lifecycle_event_to_json as _lifecycle_event_to_json,
)
from sqlbuild.runtime.observability.main.log_stream_scope import (
    log_stream_scope as _log_stream_scope,
)
from sqlbuild.runtime.observability.main.operation_scope import operation_scope as _operation_scope
from sqlbuild.runtime.observability.main.resource_attempt_scope import (
    resource_attempt_scope as _resource_attempt_scope,
)
from sqlbuild.runtime.observability.main.run_scope import run_scope as _run_scope
from sqlbuild.runtime.observability.main.statement_scope import statement_scope as _statement_scope
from sqlbuild.runtime.observability.main.validate_idempotent_duplicate import (
    validate_idempotent_duplicate as _validate_idempotent_duplicate,
)
from sqlbuild.runtime.observability.models import (
    DiagnosticLog,
    ExecutionIdentity,
    LifecycleEvent,
    OpaqueLifecycleEvent,
)

__all__ = (
    "DiagnosticLog",
    "ExecutionIdentity",
    "LifecycleEvent",
    "ObservabilityValidationError",
    "OpaqueLifecycleEvent",
    "diagnostic_log_from_json",
    "diagnostic_log_to_json",
    "current_execution_identity",
    "execution_identity_to_dict",
    "identity_scope",
    "invocation_scope",
    "is_terminal_event",
    "lifecycle_event_from_json",
    "lifecycle_event_to_json",
    "log_stream_scope",
    "operation_scope",
    "resource_attempt_scope",
    "run_scope",
    "statement_scope",
    "validate_idempotent_duplicate",
)


def current_execution_identity() -> ExecutionIdentity | None:
    """Return the identity installed in the current context, if any."""

    return _current_execution_identity()


def execution_identity_to_dict(identity: ExecutionIdentity) -> dict[str, str | None]:
    """Return language-neutral identity fields without transforming IDs."""

    return _execution_identity_to_dict(identity)


@contextmanager
def identity_scope(identity: ExecutionIdentity) -> Iterator[ExecutionIdentity]:
    """Install an explicit immutable identity snapshot for a nested boundary."""

    with _identity_scope(identity) as installed:
        yield installed


@contextmanager
def invocation_scope(invocation_id: str | None = None) -> Iterator[ExecutionIdentity]:
    """Install a new invocation identity, generating its ID when omitted."""

    with _invocation_scope(invocation_id) as identity:
        yield identity


@contextmanager
def run_scope(run_id: str) -> Iterator[ExecutionIdentity]:
    """Install a run while preserving or creating its invocation identity."""

    with _run_scope(run_id) as identity:
        yield identity


@contextmanager
def resource_attempt_scope(
    *, resource_id: str, resource_attempt_id: str | None = None
) -> Iterator[ExecutionIdentity]:
    """Install separate resource and resource-attempt identities."""

    with _resource_attempt_scope(
        resource_id=resource_id, resource_attempt_id=resource_attempt_id
    ) as identity:
        yield identity


@contextmanager
def operation_scope(operation_id: str | None = None) -> Iterator[ExecutionIdentity]:
    """Install an operation identity, generating its ID when omitted."""

    with _operation_scope(operation_id) as identity:
        yield identity


@contextmanager
def statement_scope(statement_id: str | None = None) -> Iterator[ExecutionIdentity]:
    """Install a statement identity, generating its ID when omitted."""

    with _statement_scope(statement_id) as identity:
        yield identity


@contextmanager
def log_stream_scope(log_stream_id: str | None = None) -> Iterator[ExecutionIdentity]:
    """Install a distinct diagnostic log-stream identity."""

    with _log_stream_scope(log_stream_id) as identity:
        yield identity


def lifecycle_event_from_json(raw_json: str) -> LifecycleEvent | OpaqueLifecycleEvent:
    """Decode known lifecycle events and retain unknown envelopes opaquely."""

    return _lifecycle_event_from_json(raw_json)


def lifecycle_event_to_json(event: LifecycleEvent | OpaqueLifecycleEvent) -> str:
    """Serialize a known or opaque lifecycle event deterministically."""

    return _lifecycle_event_to_json(event)


def diagnostic_log_from_json(raw_json: str) -> DiagnosticLog:
    """Decode and validate a structured diagnostic log."""

    return _diagnostic_log_from_json(raw_json)


def diagnostic_log_to_json(log: DiagnosticLog) -> str:
    """Serialize a structured diagnostic log deterministically."""

    return _diagnostic_log_to_json(log)


def is_terminal_event(event: LifecycleEvent) -> bool:
    """Return whether the fact closes its correlated lifecycle scope."""

    return _is_terminal_event(event)


def validate_idempotent_duplicate(*, original: LifecycleEvent, duplicate: LifecycleEvent) -> None:
    """Assert that a repeated event ID identifies exactly the same immutable fact."""

    _ = _validate_idempotent_duplicate(original=original, duplicate=duplicate)
