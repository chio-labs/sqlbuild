"""Output capture stream and exporter contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild.runtime.output_capture.models import OutputRecord


class OutputStream(StrEnum):
    """Process text streams captured at the command boundary."""

    STDOUT = "stdout"
    STDERR = "stderr"


class OutputRecordPriority(StrEnum):
    """Queue retention classes for captured records."""

    BULK = "bulk"
    TERMINAL = "terminal"


class OutputBatchExporter(Protocol):
    """Destination-owned batch publisher, commonly backed by Kafka."""

    def export_output(self, records: tuple[OutputRecord, ...]) -> object: ...
