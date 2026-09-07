"""Invocation lifecycle metadata scope entrypoint."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from sqlbuild.runtime.observability._helpers.identity import (
    invocation_external_context_scope as _invocation_external_context_scope,
)
from sqlbuild.runtime.observability.types import JSONValue


@contextmanager
def invocation_external_context_scope(
    *, external_context: Mapping[str, object]
) -> Iterator[Mapping[str, JSONValue]]:
    """Install validated integration context for lifecycle event creation."""

    with _invocation_external_context_scope(external_context=external_context) as installed:
        yield installed
