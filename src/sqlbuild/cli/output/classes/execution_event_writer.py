"""Thread-safe JSON Lines execution event writer."""

from __future__ import annotations

import os
import threading
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.output.classes.compatibility_event_projector import (
    CompatibilityEventProjector,
    current_compatibility_event_projector,
)
from sqlbuild.cli.output.constants import EXECUTION_EVENT_PATH_ENV
from sqlbuild.cli.output.main._build_item_execution_event import format_build_item_execution_event
from sqlbuild.cli.output.main._clone_item_execution_event import format_clone_item_execution_event
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.clone.models import CloneItemResult


class ExecutionEventWriter:
    """Append and flush structured execution events for a parent integration."""

    def __init__(self, *, path: Path | None = None) -> None:
        configured_path: str | None = os.environ.get(EXECUTION_EVENT_PATH_ENV)
        self._path: Path | None = path or (Path(configured_path) if configured_path else None)
        self._stream: TextIO | None = None
        self._lock: threading.Lock = threading.Lock()
        self._projector: CompatibilityEventProjector | None = (
            current_compatibility_event_projector()
        )
        self._closed: bool = False
        if self._projector is not None:
            self._projector.register_writer(path=self._path)
        if self._path is not None:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._stream = self._path.open(mode="a", encoding="utf-8")
            except BaseException:
                if self._projector is not None:
                    with self._projector.output_serialization_scope():
                        _ = self._projector.unregister_writer()
                raise

    def write_build_result(
        self, *, result: object, plan: PlanOutput | None, command: str = "build"
    ) -> None:
        """Project canonical terminal evidence plus build-result enrichment to v1."""

        with self._lock:
            if self._closed or self._stream is None:
                return
            with self._output_scope():
                payload: str | None = format_build_item_execution_event(
                    result=result, plan=plan, command=command
                )
                self._write_payload(payload)

    def write_clone_result(self, *, item: CloneItemResult, resource_type: str) -> None:
        """Project canonical terminal evidence plus clone-result enrichment to v1."""

        with self._lock:
            if self._closed or self._stream is None:
                return
            with self._output_scope():
                payload: str = format_clone_item_execution_event(
                    item=item, resource_type=resource_type
                )
                self._write_payload(payload)

    def _write_payload(self, payload: str | None) -> None:
        if self._stream is None or not payload:
            return
        self._stream.write(payload)
        self._stream.flush()

    def _output_scope(self) -> AbstractContextManager[None]:
        if self._projector is None:
            return nullcontext()
        return self._projector.output_serialization_scope()

    def close(self) -> None:
        """Close the event stream when configured."""

        with self._lock:
            if self._closed:
                return
            with self._output_scope():
                self._closed = True
                if self._projector is not None:
                    self._write_payload(self._projector.unregister_writer())
                if self._stream is not None:
                    self._stream.close()
                self._stream = None
