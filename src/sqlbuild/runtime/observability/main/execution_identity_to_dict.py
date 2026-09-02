"""Execution identity serialization entrypoint."""

from sqlbuild.runtime.observability._helpers.identity import (
    execution_identity_to_dict as _execution_identity_to_dict,
)
from sqlbuild.runtime.observability.models import ExecutionIdentity


def execution_identity_to_dict(identity: ExecutionIdentity) -> dict[str, str | None]:
    """Return language-neutral identity fields without transforming IDs."""

    return _execution_identity_to_dict(identity)
