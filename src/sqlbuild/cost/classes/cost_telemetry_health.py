"""Process-local telemetry failure tracking for the active build."""

import threading


class CostTelemetryHealth:
    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._ledger_failures: dict[str, str] = {}

    def mark_ledger_failure(self, *, run_id: str, error: Exception) -> None:
        with self._lock:
            self._ledger_failures.setdefault(run_id, type(error).__name__)

    def consume_ledger_failure(self, *, run_id: str) -> str | None:
        with self._lock:
            return self._ledger_failures.pop(run_id, None)
