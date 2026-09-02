"""Explicit execution identity binding entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.observability._helpers.identity import identity_scope as _identity_scope
from sqlbuild.runtime.observability.models import ExecutionIdentity


@contextmanager
def identity_scope(identity: ExecutionIdentity) -> Iterator[ExecutionIdentity]:
    """Install an explicit immutable identity snapshot for a nested boundary."""

    with _identity_scope(identity) as installed:
        yield installed
