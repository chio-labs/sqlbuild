"""Shared decisions for observed DB-API proxies."""

from collections.abc import Sized
from typing import Any

from sqlbuild.runtime.observability.main.current_execution_identity import (
    current_execution_identity,
)
from sqlbuild.runtime.observability.models import ExecutionIdentity


def batch_size(*, args: tuple[Any, ...]) -> int | None:
    """Return a safe batch size without consuming an input iterable."""

    if not args or isinstance(args[0], (str, bytes, bytearray)) or not isinstance(args[0], Sized):
        return None
    return len(args[0])


def statement_is_active() -> bool:
    """Return whether an outer adapter boundary already owns the statement."""

    identity: ExecutionIdentity | None = current_execution_identity()
    return identity is not None and identity.statement_id is not None
