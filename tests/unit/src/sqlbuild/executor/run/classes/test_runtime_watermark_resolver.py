from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor

import pytest

from sqlbuild.executor.run.classes.runtime_watermark_resolver import RuntimeWatermarkResolver
from tests.unit.src.sqlbuild.executor.run.classes._test_types import (
    RuntimeWatermarkResolverTestCase,
)


class _BlockingQuery:
    def __init__(self) -> None:
        self.started: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()
        self.count = 0

    def __call__(self) -> tuple[object | None, object | None]:
        self.count += 1
        self.started.set()
        self.release.wait(timeout=5)
        return 10, 20


class _FailingQuery:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> tuple[object | None, object | None]:
        self.count += 1
        raise RuntimeError("warehouse unavailable")


class _ImmediateQuery:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> tuple[object | None, object | None]:
        self.count += 1
        return None, 30


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeWatermarkResolverTestCase(
            description="concurrent consumers share one exact physical read",
            expected_query_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_two_consumers_when_resolving_same_watermark_then_query_executes_once(
    test_case: RuntimeWatermarkResolverTestCase,
) -> None:
    resolver: RuntimeWatermarkResolver = RuntimeWatermarkResolver()
    query: _BlockingQuery = _BlockingQuery()
    executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=2)
    first: Future[tuple[object | None, object | None]] = executor.submit(
        resolver.resolve,
        relation="raw.orders",
        cursor_column="event_time",
        read_minimum=True,
        query=query,
    )
    query.started.wait(timeout=5)
    second: Future[tuple[object | None, object | None]] = executor.submit(
        resolver.resolve,
        relation="raw.orders",
        cursor_column="event_time",
        read_minimum=True,
        query=query,
    )
    query.release.set()

    assert first.result(timeout=5) == (10, 20)
    assert second.result(timeout=5) == (10, 20)
    assert query.count == test_case.expected_query_count
    executor.shutdown(wait=True)


@pytest.mark.parametrize(
    "test_case",
    [
        RuntimeWatermarkResolverTestCase(
            description="failed physical read is cached without in-run retry",
            expected_query_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cached_failure_when_second_consumer_resolves_then_same_failure_is_raised(
    test_case: RuntimeWatermarkResolverTestCase,
) -> None:
    resolver: RuntimeWatermarkResolver = RuntimeWatermarkResolver()
    query: _FailingQuery = _FailingQuery()

    with pytest.raises(RuntimeError, match="warehouse unavailable"):
        resolver.resolve(
            relation="raw.orders",
            cursor_column="event_time",
            read_minimum=False,
            query=query,
        )
    with pytest.raises(RuntimeError, match="warehouse unavailable"):
        resolver.resolve(
            relation="raw.orders",
            cursor_column="event_time",
            read_minimum=False,
            query=query,
        )

    assert query.count == test_case.expected_query_count
    next_run_resolver: RuntimeWatermarkResolver = RuntimeWatermarkResolver()
    retry_query: _ImmediateQuery = _ImmediateQuery()
    retry_result: tuple[object | None, object | None] = next_run_resolver.resolve(
        relation="raw.orders",
        cursor_column="event_time",
        read_minimum=False,
        query=retry_query,
    )
    assert retry_result == (None, 30)
    assert retry_query.count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
