"""Process-wide delivery of template input reads to the active compile recorders."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads
from sqlbuild.compiler.compile.types import CompileContextKey


class CompileInputReadRegistry:
    """Deliver template reads from every thread, including ones without copied context."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._recorders: tuple[CompileInputReads, ...] = ()

    @contextmanager
    def recording(self) -> Iterator[CompileInputReads]:
        """Record environment variables and run-identity reads until the block exits."""

        recorder: CompileInputReads = CompileInputReads()
        with self._lock:
            self._recorders = (*self._recorders, recorder)
        try:
            yield recorder
        finally:
            with self._lock:
                self._recorders = tuple(item for item in self._recorders if item is not recorder)

    def environment_read(self, name: str) -> None:
        """Note that a template looked up one environment variable, present or not."""

        for recorder in self._recorders:
            recorder.add_environment_name(name)

    def settings_class_read(self, settings_class: type) -> None:
        """Note a provider settings class instantiated from the environment and files."""

        for recorder in self._recorders:
            recorder.add_settings_class(settings_class)

    def context_read(self, name: str) -> None:
        """Note a CTX lookup; only the per-invocation run identity is volatile."""

        if name != CompileContextKey.RUN_ID:
            return
        for recorder in self._recorders:
            recorder.mark_run_id_read()
