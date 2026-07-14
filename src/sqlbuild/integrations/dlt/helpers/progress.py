"""dlt progress collector for SQLBuild source loaders."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlbuild.integrations.dlt.constants import DLT_FORCE_PROGRESS_COUNTER_NAMES
from sqlbuild.integrations.dlt.models import DltProgressCounter, DltProgressEvent


class SqlbuildDltProgressCollector:
    """Collector compatible with dlt's progress collector protocol."""

    def __init__(self, *, on_progress: Callable[[str], None] | None = None) -> None:
        self.step: str = ""
        self.events: list[DltProgressEvent] = []
        self._counters: dict[tuple[str, str, str | None], DltProgressCounter] = {}
        self._on_progress: Callable[[str], None] | None = on_progress
        self._last_live_message: str = ""
        self._last_live_at: float = 0.0

    def __call__(self, step: str) -> SqlbuildDltProgressCollector:
        self.step = step
        return self

    def __enter__(self) -> SqlbuildDltProgressCollector:
        self._start(self.step)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any
    ) -> None:
        self._stop()

    def on_start_trace(self, trace: Any, step: Any, pipeline: Any) -> None:
        return None

    def on_start_trace_step(self, trace: Any, step: Any, pipeline: Any) -> None:
        return None

    def on_end_trace_step(
        self, trace: Any, step: Any, pipeline: Any, step_info: Any, send_state: bool
    ) -> None:
        return None

    def on_end_trace(self, trace: Any, pipeline: Any, send_state: bool) -> None:
        return None

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int | None = None,
        inc_total: int | None = None,
        message: str | None = None,
        label: str | None = None,
    ) -> None:
        event: DltProgressEvent = DltProgressEvent(
            step=self.step,
            name=name,
            inc=inc,
            total=total,
            inc_total=inc_total,
            message=message,
            label=label,
        )
        self.events.append(event)
        key: tuple[str, str, str | None] = (self.step, name, label)
        counter: DltProgressCounter = self._counters.setdefault(
            key,
            DltProgressCounter(step=self.step, name=name, label=label, total=total),
        )
        counter.count += inc
        if total is not None:
            counter.total = total
        if inc_total is not None:
            counter.total = (counter.total or 0) + inc_total
        if message is not None:
            counter.message = message
        self._emit_live_progress(counter)

    def _start(self, step: str) -> None:
        self.step = step
        self._emit_live_message(message=f"dlt {self._display_step(step)}", force=True)

    def _stop(self) -> None:
        return None

    def format_summary(self) -> str:
        if not self._counters:
            return ""
        lines: list[str] = ["dlt progress"]
        step: str
        for step in self._ordered_steps():
            rendered: str = self._format_step(step)
            if rendered:
                lines.append(f"{self._display_step(step)}: {rendered}")
        return "\n".join(lines)

    def _emit_live_progress(self, counter: DltProgressCounter) -> None:
        message: str = f"dlt {self._display_step(counter.step)}: {self._format_counter(counter)}"
        self._emit_live_message(
            message=message, force=counter.name in DLT_FORCE_PROGRESS_COUNTER_NAMES
        )

    def _emit_live_message(self, *, message: str, force: bool = False) -> None:
        if self._on_progress is None:
            return
        now: float = time.monotonic()
        if not force and message == self._last_live_message:
            return
        live_refresh_interval_seconds: float = 0.5
        if not force and now - self._last_live_at < live_refresh_interval_seconds:
            return
        self._last_live_message = message
        self._last_live_at = now
        self._on_progress(message)

    def _ordered_steps(self) -> tuple[str, ...]:
        ordered: list[str] = []
        event: DltProgressEvent
        for event in self.events:
            if event.step not in ordered:
                ordered.append(event.step)
        return tuple(ordered)

    def _format_step(self, step: str) -> str:
        counters: list[DltProgressCounter] = [
            counter for counter in self._counters.values() if counter.step == step
        ]
        counters.sort(
            key=lambda counter: (counter.name.startswith("_"), counter.name, counter.label or "")
        )
        return ", ".join(self._format_counter(counter) for counter in counters if counter.count)

    def _display_step(self, step: str) -> str:
        normalized: str = step.strip().lower()
        if normalized.startswith("extract"):
            return "extract"
        if normalized.startswith("normalize"):
            return "normalize"
        if normalized.startswith("load"):
            return "load"
        return normalized or "dlt"

    def _format_counter(self, counter: DltProgressCounter) -> str:
        name: str = counter.name if counter.label is None else f"{counter.name} ({counter.label})"
        value: str = (
            f"{counter.count}/{counter.total}" if counter.total is not None else f"{counter.count}"
        )
        if counter.message is not None:
            return f"{name} {value} [{counter.message}]"
        return f"{name} {value}"
