"""Calculate retry delays for Python-node execution."""

import random

from sqlbuild.python_nodes.models import RetryPolicy


def calculate_retry_delay(*, retry_policy: RetryPolicy, retry_index: int) -> float:
    """Calculate the delay before a retry attempt."""

    delay_seconds: float = retry_policy.initial_delay_seconds * (
        retry_policy.backoff_multiplier**retry_index
    )
    if retry_policy.max_delay_seconds is not None:
        delay_seconds = min(delay_seconds, retry_policy.max_delay_seconds)
    if retry_policy.jitter:
        return random.uniform(0, delay_seconds)
    return delay_seconds
