"""Invocation-scoped native CLI projection of canonical lifecycle facts."""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from collections.abc import Mapping
from contextvars import ContextVar, Token
from typing import TextIO, cast

from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.runtime.observability.constants import RESOURCE_TERMINALS, RETRY_SCHEDULED_EVENT
from sqlbuild.runtime.observability.models import LifecycleEvent

_VISIBLE_OPERATION_LABELS: Mapping[str, str] = {
    "discovery_declaration_parse": "Declaration parsing",
    "discovery_filesystem_walk": "Filesystem discovery",
    "discovery_project_assembly": "Project assembly",
    "discovery_python_import": "Python discovery",
    "external_manifest_discovery": "External manifest discovery",
    "project_discovery": "Project discovery",
    "project_compile": "Project compile",
    "dbt_command": "dbt command",
    "external_source_load": "loader callable",
    "ingestr_command": "ingestr subprocess",
    "managed_source_load": "loader callable",
    "python_asset": "Python asset attempt",
    "python_check": "Python check attempt",
    "python_hook": "Python hook",
    "python_task": "Python task attempt",
    "sql_hook": "SQL hook",
}
_RESOURCE_START: str = "resource_attempt_started"
_OPERATION_START: str = "operation_started"
_OPERATION_TERMINALS: frozenset[str] = frozenset({"operation_completed", "operation_failed"})


class NativeProgressProjector:
    """Project canonical starts and correlate enriched terminal presentation."""

    def __init__(self, *, stream: TextIO, use_color: bool) -> None:
        self._stream: TextIO = stream
        self._style: CliStyle = CliStyle(use_color=use_color)
        self._is_tty: bool = hasattr(stream, "isatty") and stream.isatty()
        self._lock: threading.RLock = threading.RLock()
        self._seen_event_ids: set[str] = set()
        self._resource_ordinals: dict[str, int] = {}
        self._resource_total: int = 0
        self._attempts_by_id: dict[str, LifecycleEvent] = {}
        self._pending_terminal_ids_by_resource: defaultdict[str, deque[str]] = defaultdict(deque)
        self._resource_ids_by_name: defaultdict[str, set[str]] = defaultdict(set)
        self._rendered_terminal_ids: set[str] = set()
        self._operation_starts: dict[str, LifecycleEvent] = {}
        self._enriched_resource_names: set[str] = set()

    def install(self) -> Token[NativeProgressProjector | None]:
        """Install this projector for presentation adapters in the invocation context."""

        return _CURRENT_PROJECTOR.set(self)

    def restore(self, token: Token[NativeProgressProjector | None]) -> None:
        """Restore the previous invocation projector."""

        _CURRENT_PROJECTOR.reset(token)

    def configure_resources(self, *, ordinals: Mapping[str, int], total: int) -> None:
        """Add safe display order metadata without changing canonical facts."""

        with self._lock:
            self._resource_ordinals.update(ordinals)
            self._resource_total = max(self._resource_total, total)
            self._enriched_resource_names.update(ordinals)

    def expect_resource_enrichment(self, *, resource_name: str) -> None:
        """Declare that an existing result callback will enrich this resource terminal."""

        with self._lock:
            self._enriched_resource_names.add(resource_name)

    def is_operation_active(self, *, operation_name: str) -> bool:
        """Return whether a visible canonical operation currently owns progress."""

        with self._lock:
            return any(
                event.payload.get("operation_name") == operation_name
                for event in self._operation_starts.values()
            )

    def consume(self, event: LifecycleEvent) -> None:
        """Consume one known lifecycle fact idempotently."""

        with self._lock:
            if event.event_id in self._seen_event_ids:
                return
            self._seen_event_ids.add(event.event_id)
            if event.event_type == _RESOURCE_START:
                self._consume_resource_start(event)
            elif event.event_type in RESOURCE_TERMINALS:
                self._consume_resource_terminal(event)
            elif event.event_type == _OPERATION_START:
                self._consume_operation_start(event)
            elif event.event_type in _OPERATION_TERMINALS:
                self._consume_operation_terminal(event)
            elif event.event_type == RETRY_SCHEDULED_EVENT:
                self._consume_retry_scheduled(event)

    def consume_resource_terminal(
        self,
        *,
        resource_name: str,
        resource_id: str | None = None,
        resource_attempt_id: str | None = None,
        attempt_number: int | None = None,
    ) -> float | None:
        """Claim the targeted or latest terminal for one final resource result."""

        with self._lock:
            resolved_resource_id, pending, candidates, target = self._resolve_resource_terminal(
                resource_name=resource_name,
                resource_id=resource_id,
                resource_attempt_id=resource_attempt_id,
                attempt_number=attempt_number,
            )
            if resolved_resource_id is None or pending is None or target is None:
                return None
            target_attempt_id: str | None = target.resource_attempt_id
            if target_attempt_id is None:
                return None
            for event in candidates:
                if event is target:
                    break
                self._render_resource_terminal(event=event, resource_name=resource_name)
            self._rendered_terminal_ids.add(target_attempt_id)
            self._remove_claimed_terminals(pending=pending, target=target)
            duration: object = target.payload.get("duration_ms")
            return float(duration) if isinstance(duration, int | float) else None

    def resource_terminal_duration(
        self,
        *,
        resource_name: str,
        resource_id: str | None = None,
        resource_attempt_id: str | None = None,
        attempt_number: int | None = None,
    ) -> float | None:
        """Return a terminal duration without claiming its presentation."""

        with self._lock:
            _, _, _, target = self._resolve_resource_terminal(
                resource_name=resource_name,
                resource_id=resource_id,
                resource_attempt_id=resource_attempt_id,
                attempt_number=attempt_number,
            )
            if target is None:
                return None
            duration: object = target.payload.get("duration_ms")
            return float(duration) if isinstance(duration, int | float) else None

    def close(self) -> None:
        """Restore terminal cursor state without inventing missing terminal rows."""

        with self._lock:
            event: LifecycleEvent
            for event in self._attempts_by_id.values():
                if event.event_type not in RESOURCE_TERMINALS:
                    continue
                resource_name: object = event.payload.get("resource_name")
                if isinstance(resource_name, str):
                    self._render_resource_terminal(event=event, resource_name=resource_name)

    def _consume_resource_start(self, event: LifecycleEvent) -> None:
        attempt_id: str | None = event.resource_attempt_id
        resource_id: str | None = event.resource_id
        resource_name: object = event.payload.get("resource_name")
        resource_kind: object = event.payload.get("resource_kind")
        if (
            attempt_id is None
            or resource_id is None
            or not isinstance(resource_name, str)
            or not isinstance(resource_kind, str)
        ):
            return
        self._resource_ids_by_name[resource_name].add(resource_id)
        self._render_prior_attempts(resource_id=resource_id, resource_name=resource_name)
        self._attempts_by_id[attempt_id] = event
        if self._is_tty and resource_name in self._enriched_resource_names:
            return
        ordinal: int | None = self._resource_ordinals.get(resource_name)
        counter: str = ""
        if ordinal is not None and self._resource_total > 0:
            counter = f"{ordinal}/{self._resource_total}  "
        status: str = self._style.status(status="START")
        self._write(f"  {counter}{resource_kind:<10}{resource_name} {status}")

    def _consume_resource_terminal(self, event: LifecycleEvent) -> None:
        attempt_id: str | None = event.resource_attempt_id
        resource_id: str | None = event.resource_id
        resource_name: object = event.payload.get("resource_name")
        if attempt_id is None or resource_id is None or not isinstance(resource_name, str):
            return
        self._resource_ids_by_name[resource_name].add(resource_id)
        self._attempts_by_id[attempt_id] = event
        self._pending_terminal_ids_by_resource[resource_id].append(attempt_id)
        if resource_name not in self._enriched_resource_names:
            self._render_resource_terminal(event=event, resource_name=resource_name)

    def _render_resource_terminal(self, *, event: LifecycleEvent, resource_name: str) -> None:
        attempt_id: str | None = event.resource_attempt_id
        if attempt_id is None or attempt_id in self._rendered_terminal_ids:
            return
        self._rendered_terminal_ids.add(attempt_id)
        resource_kind: object = event.payload.get("resource_kind")
        if not isinstance(resource_kind, str):
            return
        status_text: str = (
            "FAIL"
            if event.event_type.endswith("failed")
            else "SKIP"
            if event.event_type.endswith("skipped")
            else "OK"
        )
        status: str = self._style.status(status=status_text)
        duration: object = event.payload.get("duration_ms")
        elapsed: str = (
            f" {float(duration) / 1000.0:.2f}s" if isinstance(duration, int | float) else ""
        )
        self._write(f"  {resource_kind:<10}{resource_name} {status}{elapsed}")

    def _render_prior_attempts(self, *, resource_id: str, resource_name: str) -> None:
        pending: deque[str] = self._pending_terminal_ids_by_resource[resource_id]
        while pending:
            attempt_id: str = pending.popleft()
            event: LifecycleEvent | None = self._attempts_by_id.get(attempt_id)
            if event is not None:
                self._render_resource_terminal(event=event, resource_name=resource_name)

    def _pending_terminal_events(self, *, pending: deque[str]) -> list[LifecycleEvent]:
        events: list[LifecycleEvent] = []
        for attempt_id in pending:
            if attempt_id in self._rendered_terminal_ids:
                continue
            event: LifecycleEvent | None = self._attempts_by_id.get(attempt_id)
            if event is not None:
                events.append(event)
        return events

    def _remove_claimed_terminals(self, *, pending: deque[str], target: LifecycleEvent) -> None:
        while pending:
            attempt_id: str = pending.popleft()
            if attempt_id == target.resource_attempt_id:
                return

    def _single_resource_id(self, *, resource_name: str) -> str | None:
        resource_ids: set[str] = self._resource_ids_by_name[resource_name]
        if len(resource_ids) != 1:
            return None
        return next(iter(resource_ids))

    def _resolve_resource_terminal(
        self,
        *,
        resource_name: str,
        resource_id: str | None,
        resource_attempt_id: str | None,
        attempt_number: int | None,
    ) -> tuple[str | None, deque[str] | None, list[LifecycleEvent], LifecycleEvent | None]:
        resolved_resource_id: str | None = resource_id or self._single_resource_id(
            resource_name=resource_name
        )
        if resolved_resource_id is None:
            return None, None, [], None
        pending: deque[str] = self._pending_terminal_ids_by_resource[resolved_resource_id]
        candidates: list[LifecycleEvent] = self._pending_terminal_events(pending=pending)
        target: LifecycleEvent | None = _claim_target(
            candidates=candidates,
            resource_attempt_id=resource_attempt_id,
            attempt_number=attempt_number,
        )
        return resolved_resource_id, pending, candidates, target

    def _consume_operation_start(self, event: LifecycleEvent) -> None:
        operation_id: str | None = event.operation_id
        operation_name: object = event.payload.get("operation_name")
        if (
            operation_id is None
            or not isinstance(operation_name, str)
            or operation_name not in _VISIBLE_OPERATION_LABELS
            or (self._is_tty and event.resource_attempt_id is None)
        ):
            return
        self._operation_starts[operation_id] = event
        status: str = self._style.status(status="START")
        prefix: str = "    " if event.resource_attempt_id is not None else ""
        attempt: str = _operation_attempt_label(event)
        self._write(f"{prefix}{_VISIBLE_OPERATION_LABELS[operation_name]}{attempt}  {status}")

    def _consume_operation_terminal(self, event: LifecycleEvent) -> None:
        operation_id: str | None = event.operation_id
        if operation_id is None or operation_id not in self._operation_starts:
            return
        start: LifecycleEvent = self._operation_starts.pop(operation_id)
        operation_name: object = start.payload.get("operation_name")
        if not isinstance(operation_name, str):
            return
        status_text: str = "FAIL" if event.event_type.endswith("failed") else "OK"
        status: str = self._style.status(status=status_text)
        duration: object = event.payload.get("duration_ms")
        elapsed: str = (
            f"  ({float(duration) / 1000.0:.2f}s)" if isinstance(duration, int | float) else ""
        )
        prefix: str = "    " if event.resource_attempt_id is not None else ""
        attempt: str = _operation_attempt_label(start)
        self._write(
            f"{prefix}{_VISIBLE_OPERATION_LABELS[operation_name]}{attempt}  {status}{elapsed}"
        )

    def _consume_retry_scheduled(self, event: LifecycleEvent) -> None:
        failed_attempt: object = event.payload.get("failed_attempt_number")
        next_attempt: object = event.payload.get("next_attempt_number")
        delay_ms: object = event.payload.get("delay_ms")
        if isinstance(failed_attempt, bool) or not isinstance(failed_attempt, int):
            return
        if isinstance(next_attempt, bool) or not isinstance(next_attempt, int):
            return
        if isinstance(delay_ms, bool) or not isinstance(delay_ms, int):
            return
        self._write(
            f"    retry {failed_attempt}->{next_attempt} in {float(delay_ms) / 1000.0:.2f}s"
        )

    def _write(self, line: str) -> None:
        self._stream.write(f"{line}\n")
        self._stream.flush()


_CURRENT_PROJECTOR: ContextVar[NativeProgressProjector | None] = ContextVar(
    "sqlbuild_native_progress_projector", default=None
)


def current_native_progress_projector() -> NativeProgressProjector | None:
    """Return the projector installed for the current CLI invocation."""

    return _CURRENT_PROJECTOR.get()


def _claim_target(
    *,
    candidates: list[LifecycleEvent],
    resource_attempt_id: str | None,
    attempt_number: int | None,
) -> LifecycleEvent | None:
    if resource_attempt_id is not None:
        return next(
            (event for event in candidates if event.resource_attempt_id == resource_attempt_id),
            None,
        )
    if attempt_number is not None:
        return next(
            (
                event
                for event in reversed(candidates)
                if event.payload.get("attempt_number") == attempt_number
            ),
            None,
        )
    return candidates[-1] if candidates else None


def _operation_attempt_label(event: LifecycleEvent) -> str:
    metadata: object = event.payload.get("metadata")
    if not isinstance(metadata, Mapping):
        return ""
    typed_metadata: Mapping[str, object] = cast(Mapping[str, object], metadata)
    attempt_number: object = typed_metadata.get("attempt_number")
    if isinstance(attempt_number, int) and not isinstance(attempt_number, bool):
        return f" {attempt_number}"
    return ""
