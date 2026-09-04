"""Configured event-export output capture for one CLI command."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlbuild.observability import ExecutionIdentity
from sqlbuild.runtime.output_capture.classes.dispatcher import OutputCaptureDispatcher
from sqlbuild.runtime.output_capture.classes.text_tee import TextOutputTee
from sqlbuild.runtime.output_capture.main.current_output_capture_context import (
    current_output_capture_context,
)
from sqlbuild.runtime.output_capture.models import OutputCaptureContext
from sqlbuild.runtime.output_capture.types import OutputBatchExporter, OutputStream


@contextmanager
def configured_output_capture_scope(
    *, exporter_scope: OutputBatchExporter | None, identity: ExecutionIdentity
) -> Iterator[None]:
    """Tee command streams through the configured event-export provider session."""

    if exporter_scope is None:
        yield
        return
    context: OutputCaptureContext | None = current_output_capture_context()
    try:
        dispatcher: OutputCaptureDispatcher = OutputCaptureDispatcher(
            exporter=exporter_scope,
            invocation_id=identity.invocation_id,
            run_id=identity.run_id,
            external_context=None if context is None else context.external_context,
        )
    except BaseException:
        yield
        return
    original_stdout: Any = sys.stdout
    original_stderr: Any = sys.stderr
    try:
        stdout_tee: TextOutputTee = TextOutputTee(
            sink=original_stdout, dispatcher=dispatcher, stream=OutputStream.STDOUT
        )
        stderr_tee: TextOutputTee = TextOutputTee(
            sink=original_stderr, dispatcher=dispatcher, stream=OutputStream.STDERR
        )
    except BaseException:
        try:
            _ = dispatcher.close()
        except BaseException:
            pass
        yield
        return
    sys.stdout = stdout_tee
    sys.stderr = stderr_tee
    try:
        yield
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        try:
            _ = dispatcher.close()
        except BaseException:
            pass
