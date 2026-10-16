"""Calculate retry delays for Python-node execution."""

from sqlbuild._native import retry_delay_seconds
from sqlbuild.python_nodes.models import RetryPolicy


def calculate_retry_delay(*, retry_policy: RetryPolicy, retry_index: int) -> float:
    """Calculate the delay before a retry attempt."""

    return retry_delay_seconds(retry_policy=retry_policy, retry_index=retry_index)
