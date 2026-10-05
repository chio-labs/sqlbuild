"""Volatile inputs that templates read while one compile renders the project."""

from __future__ import annotations

import threading


class CompileInputReads:
    """Environment, settings, and run-identity reads observed during one compile."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._environment_names: set[str] = set()
        self._read_run_id: bool = False
        self._settings_classes: dict[type, None] = {}

    def add_environment_name(self, name: str) -> None:
        """Record one environment variable a template looked up, present or not."""

        with self._lock:
            self._environment_names.add(name)

    def add_settings_class(self, settings_class: type) -> None:
        """Record one settings class whose values come from the environment or files."""

        with self._lock:
            self._settings_classes[settings_class] = None

    def mark_run_id_read(self) -> None:
        """Record that a template read the per-invocation run identity."""

        with self._lock:
            self._read_run_id = True

    @property
    def environment_names(self) -> tuple[str, ...]:
        """Return the recorded environment variable names in sorted order."""

        with self._lock:
            return tuple(sorted(self._environment_names))

    @property
    def settings_classes(self) -> tuple[type, ...]:
        """Return the recorded settings classes in discovery order."""

        with self._lock:
            return tuple(self._settings_classes)

    @property
    def read_run_id(self) -> bool:
        """Return whether any template read the per-invocation run identity."""

        with self._lock:
            return self._read_run_id
