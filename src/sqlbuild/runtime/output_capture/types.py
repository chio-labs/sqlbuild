"""Output capture stream and exporter contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild.runtime.output_capture.models import CommandOutputRecord


class CommandOutputStream(StrEnum):
    """Process text streams captured at the command boundary."""

    STDOUT = "stdout"
    STDERR = "stderr"


class OutputRecordPriority(StrEnum):
    """Queue retention classes for captured records."""

    BULK = "bulk"
    TERMINAL = "terminal"


class CommandOutputBatchExporter(Protocol):
    """Destination-owned batch publisher, commonly backed by Kafka."""

    def export_output(self, records: tuple[CommandOutputRecord, ...]) -> object: ...
