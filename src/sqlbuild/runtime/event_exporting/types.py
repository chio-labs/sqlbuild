"""Type declarations for destination-neutral lifecycle-event export."""

from enum import StrEnum


class LifecycleEventKind(StrEnum):
    """Stable filter dimensions for lifecycle-event sinks."""

    INVOCATION = "invocation"
    RUN = "run"
    RESOURCE = "resource"
    MICROBATCH = "microbatch"
    OPERATION = "operation"
    STATEMENT = "statement"
    RETRY = "retry"
    AUDIT = "audit"
