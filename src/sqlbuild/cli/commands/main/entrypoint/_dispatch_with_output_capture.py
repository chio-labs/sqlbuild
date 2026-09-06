"""Configured command-output capture for one CLI command."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from sqlbuild.observability import ExecutionIdentity
from sqlbuild.runtime.output_capture.classes.dispatcher import OutputCaptureDispatcher
from sqlbuild.runtime.output_capture.classes.text_tee import TextOutputTee
from sqlbuild.runtime.output_capture.main.current_output_capture_context import (
    current_output_capture_context,
)
from sqlbuild.runtime.output_capture.main.invocation_context import (
    invocation_context_from_environment,
)
from sqlbuild.runtime.output_capture.models import OutputCaptureContext
from sqlbuild.runtime.output_capture.types import (
    CommandOutputBatchExporter,
    CommandOutputStream,
)


@contextmanager
def configured_output_capture_scope(
    *,
    exporter_scope: CommandOutputBatchExporter | None,
    identity: ExecutionIdentity,
    failure_callback: Callable[[BaseException], object] | None = None,
) -> Iterator[None]:
    """Tee command streams through the configured command-output provider session."""

    if exporter_scope is None:
        yield
        return
    context: OutputCaptureContext | None = current_output_capture_context()
    try:
        external_context: Mapping[str, object] = (
            invocation_context_from_environment() if context is None else context.external_context
        )
        dispatcher: OutputCaptureDispatcher = OutputCaptureDispatcher(
            exporter=exporter_scope,
            invocation_id=identity.invocation_id,
            run_id=identity.run_id,
            external_context=external_context,
            failure_callback=failure_callback,
        )
    except BaseException as error:
        _ = _notify_failure(callback=failure_callback, error=error)
        yield
        return
    original_stdout: Any = sys.stdout
    original_stderr: Any = sys.stderr
    try:
        stdout_tee: TextOutputTee = TextOutputTee(
            sink=original_stdout,
            dispatcher=dispatcher,
            stream=CommandOutputStream.STDOUT,
        )
        stderr_tee: TextOutputTee = TextOutputTee(
            sink=original_stderr,
            dispatcher=dispatcher,
            stream=CommandOutputStream.STDERR,
        )
    except BaseException as error:
        try:
            _ = dispatcher.close()
        except BaseException:
            pass
        _ = _notify_failure(callback=failure_callback, error=error)
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


def _notify_failure(
    *, callback: Callable[[BaseException], object] | None, error: BaseException
) -> None:
    if callback is None:
        return
    try:
        _ = callback(error)
    except BaseException:
        pass
