from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from sqlbuild.runtime.observability.models import LifecycleEvent


def read_ledger(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8").strip())


class BlockingQueryCursor:
    """Expose an sfqid, then block until its submission event is observed."""

    def __init__(self) -> None:
        self.sfqid: str | None = None
        self.rowcount: int = -1
        self._release: Event = Event()

    def execute(self, sql: str, **kwargs: object) -> BlockingQueryCursor:
        del sql, kwargs
        self.sfqid = "01c-running-query-id"
        _ = self._release.wait(timeout=1.0)
        return self

    def consume(self, event: LifecycleEvent) -> None:
        handlers: dict[str, Callable[[LifecycleEvent], None]] = {
            "statement_submitted": self._release_statement
        }
        handlers.get(event.event_type, self._ignore_event)(event)

    def _release_statement(self, event: LifecycleEvent) -> None:
        del event
        self._release.set()

    @staticmethod
    def _ignore_event(event: LifecycleEvent) -> None:
        del event
