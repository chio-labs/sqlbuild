"""Current execution identity entrypoint."""

from sqlbuild.runtime.observability._helpers.identity import (
    current_execution_identity as _current_execution_identity,
)
from sqlbuild.runtime.observability.models import ExecutionIdentity


def current_execution_identity() -> ExecutionIdentity | None:
    """Return the identity installed in the current context, if any."""

    return _current_execution_identity()
