"""Operation identity scope entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.observability._helpers.identity import operation_scope as _operation_scope
from sqlbuild.runtime.observability.models import ExecutionIdentity


@contextmanager
def operation_scope(operation_id: str | None = None) -> Iterator[ExecutionIdentity]:
    """Install an operation identity, generating its ID when omitted."""

    with _operation_scope(operation_id) as identity:
        yield identity
