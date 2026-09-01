"""Lifecycle event idempotency validation entrypoint."""

from sqlbuild.runtime.observability._helpers.observability import (
    validate_idempotent_duplicate as _validate_idempotent_duplicate,
)
from sqlbuild.runtime.observability.models import LifecycleEvent


def validate_idempotent_duplicate(*, original: LifecycleEvent, duplicate: LifecycleEvent) -> None:
    """Assert that a repeated event ID identifies exactly the same immutable fact."""

    _ = _validate_idempotent_duplicate(original=original, duplicate=duplicate)
