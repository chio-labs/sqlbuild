"""Type-layer declarations for presentation."""

from enum import StrEnum
from typing import Protocol


class CompletionState(StrEnum):
    """Overall outcome state for a completion summary line."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class TransientLineOwner(Protocol):
    """A renderer that owns the transient line currently drawn in place on a terminal."""

    def clear_transient_line(self) -> None:
        """Erase the drawn transient line so a persistent line can take its place."""
        ...

    def redraw_transient_line(self) -> None:
        """Draw the transient line again below the persistent output."""
        ...
