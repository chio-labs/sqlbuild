from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

import pytest

from sqlbuild.executor.run.classes.fingerprint_writes import FingerprintWrites
from sqlbuild.executor.run.types import FingerprintTableLocation
from tests.unit.src.sqlbuild.executor.run.classes._test_types import FingerprintSetupTestCase

_LOCATION: FingerprintTableLocation = ("analytics", "orders")


@pytest.mark.parametrize(
    "test_case",
    [
        FingerprintSetupTestCase(
            description="a writer arriving during setup waits and then skips the setup",
            first_writer_finishes=True,
            expected_requests=(True, False),
        ),
        FingerprintSetupTestCase(
            description="a writer arriving during a failed setup sets the table up itself",
            first_writer_finishes=False,
            expected_requests=(True, True),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_concurrent_writers_when_setting_up_a_table_then_only_one_sets_it_up_at_a_time(
    test_case: FingerprintSetupTestCase,
) -> None:
    writes: FingerprintWrites = FingerprintWrites()
    first_entered: threading.Event = threading.Event()
    second_started: threading.Event = threading.Event()
    requests: list[bool] = []
    finish_actions: dict[bool, Callable[[bool], None]] = {
        True: lambda requested: writes.written(
            location=_LOCATION, requested_setup=requested, set_up=requested
        ),
        False: lambda _requested: None,
    }

    def first_writer() -> None:
        with writes.setting_up(location=_LOCATION) as requested:
            requests.append(requested)
            first_entered.set()
            _ = second_started.wait(timeout=5)
            finish_actions[test_case.first_writer_finishes](requested)

    def second_writer() -> None:
        _ = first_entered.wait(timeout=5)
        second_started.set()
        with writes.setting_up(location=_LOCATION) as requested:
            requests.append(requested)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures: list[Future[None]] = [pool.submit(first_writer), pool.submit(second_writer)]
        _ = [future.result(timeout=10) for future in futures]

    assert tuple(requests) == test_case.expected_requests
