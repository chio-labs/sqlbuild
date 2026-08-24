"""Virtual-state implementation of the shared microbatch event-store contract."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.microbatches.constants import (
    MICROBATCH_WRITE_ATTEMPTS,
    MICROBATCH_WRITE_RETRY_BASE_SECONDS,
)
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope
from sqlbuild.virtual.state.classes.state_backend import StateBackend


class VirtualMicrobatchEventStore:
    """Open a short-lived backend connection for each event operation."""

    def __init__(
        self,
        *,
        backend: StateBackend,
        connection_config: dict[str, object],
        schema: str,
    ) -> None:
        self._backend = backend
        self._connection_config = connection_config
        self._schema = schema

    def write(self, event: MicrobatchEvent) -> None:
        for attempt in range(MICROBATCH_WRITE_ATTEMPTS):
            connection: Any = self._backend.connect(self._connection_config)
            try:
                self._backend.append_microbatch_event(
                    connection=connection, schema=self._schema, event=event
                )
                return
            except Exception:
                if attempt + 1 == MICROBATCH_WRITE_ATTEMPTS:
                    raise
                time.sleep(MICROBATCH_WRITE_RETRY_BASE_SECONDS * (attempt + 1))
            finally:
                self._backend.close(connection)

    def read_scope_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        connection: Any = self._backend.connect(self._connection_config)
        try:
            return self._backend.read_microbatch_scope_history(
                connection=connection, schema=self._schema, scope=scope
            )
        finally:
            self._backend.close(connection)

    def read_model_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        connection: Any = self._backend.connect(self._connection_config)
        try:
            return self._backend.read_microbatch_model_history(
                connection=connection,
                schema=self._schema,
                scope=scope,
            )
        finally:
            self._backend.close(connection)
