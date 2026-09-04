"""Immutable output capture records and accounting."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlbuild.runtime.output_capture.constants import (
    OUTPUT_LINE_EVENT_TYPE,
    OUTPUT_LOSS_SUMMARY_EVENT_TYPE,
    OUTPUT_RECORD_TYPE,
)
from sqlbuild.runtime.output_capture.types import OutputRecordPriority, OutputStream


@dataclass(frozen=True)
class OutputRecord:
    """One ANSI-free line chunk ready for destination serialization."""

    invocation_id: str
    sequence: int
    timestamp: datetime
    stream: OutputStream
    message: str
    external_context: Mapping[str, object]
    run_id: str | None = None
    chunk_index: int = 0
    chunk_count: int = 1
    priority: OutputRecordPriority = OutputRecordPriority.BULK
    record_type: str = OUTPUT_RECORD_TYPE
    dropped_records: int = 0

    @property
    def event_id(self) -> str:
        """Return a deterministic destination key for this invocation sequence."""

        return f"{self.invocation_id}:output:{self.sequence}"

    @property
    def event_type(self) -> str:
        """Return the output route discriminator used by destination exporters."""

        return (
            OUTPUT_LINE_EVENT_TYPE
            if self.record_type == OUTPUT_RECORD_TYPE
            else OUTPUT_LOSS_SUMMARY_EVENT_TYPE
        )


@dataclass(frozen=True)
class OutputCaptureSummary:
    """Best-effort bounded-delivery accounting."""

    accepted: int
    delivered: int
    failed: int
    dropped: int
    queue_depth: int
    queue_capacity: int
    flush_complete: bool


@dataclass(frozen=True)
class OutputCaptureContext:
    """Opaque integration-owned context for one command."""

    external_context: Mapping[str, object]
