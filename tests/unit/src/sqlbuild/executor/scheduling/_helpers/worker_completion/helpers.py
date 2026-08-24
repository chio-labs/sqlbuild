"""Helpers for worker completion tests."""

from __future__ import annotations

import queue
from collections.abc import Callable


def build_connection_pool(connection: str) -> queue.Queue[str]:
    connection_pool: queue.Queue[str] = queue.Queue()
    connection_pool.put(connection)
    return connection_pool


def build_success_completion(key: str, result: str) -> tuple[str, str]:
    return (key, result)


def build_failure_completion(key: str, error: BaseException) -> tuple[str, str]:
    return (key, str(error))


def successful_execute(result: str) -> Callable[[object], str]:
    def _execute(connection: object) -> str:
        del connection
        return result

    return _execute


def failing_execute(message: str) -> Callable[[object], str]:
    def _execute(connection: object) -> str:
        del connection
        raise RuntimeError(message)

    return _execute


def exceptional_execute(message: str) -> Callable[[object], str]:
    def _execute(connection: object) -> str:
        del connection
        raise KeyboardInterrupt(message)

    return _execute
