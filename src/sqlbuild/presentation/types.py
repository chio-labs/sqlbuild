"""Type-layer declarations for presentation."""

from enum import StrEnum


class CompletionState(StrEnum):
    """Overall outcome state for a completion summary line."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
