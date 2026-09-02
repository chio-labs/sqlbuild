"""Resource-attempt identity scope entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.observability._helpers.identity import (
    resource_attempt_scope as _resource_attempt_scope,
)
from sqlbuild.runtime.observability.models import ExecutionIdentity


@contextmanager
def resource_attempt_scope(
    *, resource_id: str, resource_attempt_id: str | None = None
) -> Iterator[ExecutionIdentity]:
    """Install separate resource and resource-attempt identities."""

    with _resource_attempt_scope(
        resource_id=resource_id, resource_attempt_id=resource_attempt_id
    ) as identity:
        yield identity
