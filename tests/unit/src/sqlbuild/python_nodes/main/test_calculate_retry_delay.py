import random

import pytest

from sqlbuild.python_nodes.main.calculate_retry_delay import calculate_retry_delay
from sqlbuild.python_nodes.models import RetryPolicy
from tests.unit.src.sqlbuild.python_nodes.main._test_types import (
    JitteredRetryDelayTestCase,
    RetryDelayTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RetryDelayTestCase(
            description="first retry waits the initial delay",
            policy=RetryPolicy(jitter=False),
            retry_index=0,
            expected_delay=1.0,
            expected_type=float,
        ),
        RetryDelayTestCase(
            description="later retries grow by the multiplier",
            policy=RetryPolicy(jitter=False, initial_delay_seconds=0.5, backoff_multiplier=3.0),
            retry_index=2,
            expected_delay=4.5,
            expected_type=float,
        ),
        RetryDelayTestCase(
            description="the delay is capped",
            policy=RetryPolicy(jitter=False, max_delay_seconds=7.5),
            retry_index=10,
            expected_delay=7.5,
            expected_type=float,
        ),
        RetryDelayTestCase(
            description="integer settings keep an integer delay",
            policy=RetryPolicy(
                jitter=False, initial_delay_seconds=1, backoff_multiplier=2, max_delay_seconds=None
            ),
            retry_index=3,
            expected_delay=8,
            expected_type=int,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_retry_policy_when_calculating_delay_then_returns_backoff_value_and_type(
    test_case: RetryDelayTestCase,
) -> None:
    delay: float = calculate_retry_delay(
        retry_policy=test_case.policy, retry_index=test_case.retry_index
    )

    assert delay == test_case.expected_delay
    assert type(delay) is test_case.expected_type


@pytest.mark.parametrize(
    "test_case",
    [
        JitteredRetryDelayTestCase(
            description="uncapped jitter",
            policy=RetryPolicy(max_delay_seconds=None, initial_delay_seconds=2.0),
            retry_index=1,
            seed=1234,
            expected_upper_bound=4.0,
        ),
        JitteredRetryDelayTestCase(
            description="capped jitter",
            policy=RetryPolicy(max_delay_seconds=3.0),
            retry_index=5,
            seed=7,
            expected_upper_bound=3.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_jittered_policy_when_calculating_delay_then_draws_from_python_random(
    test_case: JitteredRetryDelayTestCase,
) -> None:
    random.seed(test_case.seed)
    delay: float = calculate_retry_delay(
        retry_policy=test_case.policy, retry_index=test_case.retry_index
    )
    random.seed(test_case.seed)

    assert delay == random.uniform(0, test_case.expected_upper_bound)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
