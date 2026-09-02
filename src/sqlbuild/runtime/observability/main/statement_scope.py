"""Statement identity scope entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.observability._helpers.identity import statement_scope as _statement_scope
from sqlbuild.runtime.observability.models import ExecutionIdentity


@contextmanager
def statement_scope(statement_id: str | None = None) -> Iterator[ExecutionIdentity]:
    """Install a statement identity, generating its ID when omitted."""

    with _statement_scope(statement_id) as identity:
        yield identity
