"""Public runtime observability API."""

from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.main.diagnostic_log_from_json import (
    diagnostic_log_from_json as _diagnostic_log_from_json,
)
from sqlbuild.runtime.observability.main.diagnostic_log_to_json import (
    diagnostic_log_to_json as _diagnostic_log_to_json,
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
from sqlbuild.runtime.observability.main.validate_idempotent_duplicate import (
    validate_idempotent_duplicate as _validate_idempotent_duplicate,
)
from sqlbuild.runtime.observability.models import (
    DiagnosticLog,
    LifecycleEvent,
    OpaqueLifecycleEvent,
)

__all__ = (
    "DiagnosticLog",
    "LifecycleEvent",
    "ObservabilityValidationError",
    "OpaqueLifecycleEvent",
    "diagnostic_log_from_json",
    "diagnostic_log_to_json",
    "is_terminal_event",
    "lifecycle_event_from_json",
    "lifecycle_event_to_json",
    "validate_idempotent_duplicate",
)


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
