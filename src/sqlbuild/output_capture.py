"""Public destination-neutral command output export API."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from sqlbuild.runtime.output_capture._helpers.scope import (
    output_capture_context as _output_capture_context,
)
from sqlbuild.runtime.output_capture.models import OutputCaptureSummary, OutputRecord
from sqlbuild.runtime.output_capture.types import OutputBatchExporter, OutputStream

__all__ = (
    "OutputBatchExporter",
    "OutputCaptureSummary",
    "OutputRecord",
    "OutputStream",
    "output_capture_context",
)


@contextmanager
def output_capture_context(*, external_context: Mapping[str, object]) -> Iterator[None]:
    """Attach opaque integration context to output exported by nested CLI calls."""

    with _output_capture_context(external_context=external_context):
        yield
