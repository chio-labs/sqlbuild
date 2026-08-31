"""Virtual-state implementation of the shared microbatch event-store contract."""

from __future__ import annotations

import threading
import time
from typing import Any

from sqlbuild.microbatches.constants import (
    MICROBATCH_WRITE_ATTEMPTS,
    MICROBATCH_WRITE_RETRY_BASE_SECONDS,
)
from sqlbuild.microbatches.exceptions import MicrobatchStateError
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope, MicrobatchWriteResult
from sqlbuild.virtual.state.classes.state_backend import StateBackend


class VirtualMicrobatchEventStore:
    """Serialize short-lived backend connections for each event operation."""

    def __init__(
        self,
        *,
        backend: StateBackend,
        connection_config: dict[str, object],
        schema: str,
        operation_lock: threading.Lock,
    ) -> None:
        self._backend = backend
        self._connection_config = connection_config
        self._schema = schema
        self._operation_lock = operation_lock

    def write(self, event: MicrobatchEvent) -> None:
        self.write_many((event,))

    def write_many(self, events: tuple[MicrobatchEvent, ...]) -> MicrobatchWriteResult:
        if not events:
            return MicrobatchWriteResult(total=0, inserted=0, already_existing=0)
        for attempt in range(MICROBATCH_WRITE_ATTEMPTS):
            try:
                with self._operation_lock:
                    connection: Any = self._backend.connect(self._connection_config)
                    try:
                        result: MicrobatchWriteResult = self._backend.append_microbatch_events(
                            connection=connection, schema=self._schema, events=events
                        )
                    finally:
                        self._backend.close(connection)
                return result
            except Exception:
                if attempt + 1 == MICROBATCH_WRITE_ATTEMPTS:
                    raise
                time.sleep(MICROBATCH_WRITE_RETRY_BASE_SECONDS * (attempt + 1))
        raise MicrobatchStateError("virtual microbatch event publication exhausted retries")

    def read_scope_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        with self._operation_lock:
            connection: Any = self._backend.connect(self._connection_config)
            try:
                return self._backend.read_microbatch_scope_history(
                    connection=connection, schema=self._schema, scope=scope
                )
            finally:
                self._backend.close(connection)

    def read_model_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        with self._operation_lock:
            connection: Any = self._backend.connect(self._connection_config)
            try:
                return self._backend.read_microbatch_model_history(
                    connection=connection,
                    schema=self._schema,
                    scope=scope,
                )
            finally:
                self._backend.close(connection)
