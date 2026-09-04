"""Integration-installed output exporter command context."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlbuild.runtime.output_capture.models import OutputCaptureContext

_CURRENT_CONTEXT: ContextVar[OutputCaptureContext | None] = ContextVar(
    "sqlbuild_output_capture_context", default=None
)


@contextmanager
def output_capture_context(*, external_context: Mapping[str, object]) -> Iterator[None]:
    """Attach integration context without interpreting its contents."""

    context: OutputCaptureContext = OutputCaptureContext(
        external_context=dict(external_context),
    )
    token: Token[OutputCaptureContext | None] = _CURRENT_CONTEXT.set(context)
    try:
        yield
    finally:
        _CURRENT_CONTEXT.reset(token)


def current_output_capture_context() -> OutputCaptureContext | None:
    """Return optional integration context for the active command."""

    return _CURRENT_CONTEXT.get()
