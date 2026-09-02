"""Invocation identity scope entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.observability._helpers.identity import invocation_scope as _invocation_scope
from sqlbuild.runtime.observability.models import ExecutionIdentity


@contextmanager
def invocation_scope(invocation_id: str | None = None) -> Iterator[ExecutionIdentity]:
    """Install a new invocation identity, generating its ID when omitted."""

    with _invocation_scope(invocation_id) as identity:
        yield identity
