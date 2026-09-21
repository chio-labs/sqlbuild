"""Thread-safe JSON Lines execution event writer."""

from __future__ import annotations

import os
import sys
import threading
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.output._helpers.integration_result import (
    build_clone_integration_result,
    build_degraded_integration_result,
    build_integration_result,
    result_resource_identity,
)
from sqlbuild.cli.output.classes.terminal_event_index import (
    TerminalEventIndex,
    current_terminal_event_index,
)
from sqlbuild.cli.output.constants import INTEGRATION_RESULT_PATH_ENV
from sqlbuild.cli.output.models import IntegrationResultEnvelope, TerminalEventClaim
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError


class ExecutionEventWriter:
    """Append and flush structured execution events for a parent integration."""

    def __init__(self, *, path: Path | None = None) -> None:
        configured_path: str | None = os.environ.get(INTEGRATION_RESULT_PATH_ENV)
        self._path: Path | None = path or (Path(configured_path) if configured_path else None)
        self._stream: TextIO | None = None
        self._lock: threading.Lock = threading.Lock()
        self._terminal_index: TerminalEventIndex | None = current_terminal_event_index()
        self._closed: bool = False
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = self._path.open(mode="a", encoding="utf-8")

    def write_build_result(
        self, *, result: object, plan: PlanOutput | None, command: str = "build"
    ) -> None:
        """Write canonical terminal evidence plus typed build-result enrichment."""

        with self._lock:
            if self._closed or self._stream is None:
                return
            with self._output_scope():
                resource_name, resource_id = result_resource_identity(result=result)
                claim: TerminalEventClaim | None = (
                    self._terminal_index.claim_resource_terminal(
                        resource_name=resource_name,
                        resource_id=resource_id,
                    )
                    if self._terminal_index is not None and resource_name is not None
                    else None
                )
                if claim is None:
                    return
                try:
                    envelope: IntegrationResultEnvelope | None = build_integration_result(
                        result=result,
                        terminal=claim.terminal,
                        event_sequence=claim.event_sequence,
                        plan=plan,
                        command=command,
                    )
                    self._write_envelope(envelope)
                except ObservabilityValidationError as error:
                    self._warn_degraded_output(
                        error=error,
                        execution_succeeded=claim.terminal.event_type.endswith("completed"),
                    )
                    try:
                        self._write_envelope(
                            build_degraded_integration_result(
                                result=result,
                                terminal=claim.terminal,
                                event_sequence=claim.event_sequence,
                                command=command,
                            )
                        )
                    except ObservabilityValidationError:
                        return

    def write_clone_result(self, *, item: CloneItemResult, resource_type: str) -> None:
        """Write canonical terminal evidence plus typed clone-result enrichment."""

        with self._lock:
            if self._closed or self._stream is None:
                return
            with self._output_scope():
                claim: TerminalEventClaim | None = (
                    self._terminal_index.claim_resource_terminal(
                        resource_name=item.name,
                        resource_id=f"{resource_type}:{item.name}",
                    )
                    if self._terminal_index is not None
                    else None
                )
                if claim is None:
                    return
                try:
                    self._write_envelope(
                        build_clone_integration_result(
                            item=item,
                            terminal=claim.terminal,
                            event_sequence=claim.event_sequence,
                        )
                    )
                except ObservabilityValidationError as error:
                    self._warn_degraded_output(
                        error=error,
                        execution_succeeded=claim.terminal.event_type.endswith("completed"),
                    )
                    try:
                        self._write_envelope(
                            build_degraded_integration_result(
                                result=item,
                                terminal=claim.terminal,
                                event_sequence=claim.event_sequence,
                                command="clone",
                            )
                        )
                    except ObservabilityValidationError:
                        return

    def _write_envelope(self, envelope: IntegrationResultEnvelope | None) -> None:
        if self._stream is None or envelope is None:
            return
        self._stream.write(envelope.to_json())
        self._stream.flush()

    def _output_scope(self) -> AbstractContextManager[None]:
        if self._terminal_index is None:
            return nullcontext()
        return self._terminal_index.output_serialization_scope()

    @staticmethod
    def _warn_degraded_output(
        *, error: ObservabilityValidationError, execution_succeeded: bool
    ) -> None:
        completion: str = (
            "warehouse execution completed successfully"
            if execution_succeeded
            else "execution result remains authoritative"
        )
        sys.stderr.write(f"warning: integration output degraded: {error}; {completion}\n")
        sys.stderr.flush()

    def close(self) -> None:
        """Close the event stream when configured."""

        with self._lock:
            if self._closed:
                return
            with self._output_scope():
                self._closed = True
                if self._stream is not None:
                    self._stream.close()
                self._stream = None
