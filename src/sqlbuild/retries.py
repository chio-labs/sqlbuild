"""Public retry policy API for SQLBuild Python nodes."""

from sqlbuild.python_nodes.main.calculate_retry_delay import (
    calculate_retry_delay as calculate_python_node_retry_delay,
)
from sqlbuild.python_nodes.models import RetryPolicy

__all__ = ("RetryPolicy",)


def calculate_retry_delay(*, retry_policy: RetryPolicy, retry_index: int) -> float:
    """Calculate the delay before a retry attempt."""

    return calculate_python_node_retry_delay(
        retry_policy=retry_policy,
        retry_index=retry_index,
    )
