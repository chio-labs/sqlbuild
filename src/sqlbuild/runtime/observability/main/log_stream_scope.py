"""Diagnostic log-stream identity scope entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.observability._helpers.identity import log_stream_scope as _log_stream_scope
from sqlbuild.runtime.observability.models import ExecutionIdentity


@contextmanager
def log_stream_scope(log_stream_id: str | None = None) -> Iterator[ExecutionIdentity]:
    """Install a distinct diagnostic log-stream identity."""

    with _log_stream_scope(log_stream_id) as identity:
        yield identity
