"""Thread-level serialization for audit-result schema initialization."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock

_audit_result_ddl_lock: Lock = Lock()


def run_with_audit_result_ddl_lock(callback: Callable[[], None]) -> None:
    """Run audit-result DDL under a process-local lock."""

    with _audit_result_ddl_lock:
        callback()
