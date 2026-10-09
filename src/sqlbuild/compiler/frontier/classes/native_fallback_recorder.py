"""Debug-only count of the native fallbacks and native answers of one process, written at exit."""

from __future__ import annotations

import atexit
import json
import os
import threading
from collections import Counter
from pathlib import Path

from sqlbuild.compiler.frontier.constants import NATIVE_FALLBACK_RECORD_PREFIX
from sqlbuild.compiler.sql_analysis.constants import ANALYSIS_RECORD_DIR_ENV_VAR


class NativeFallbackRecorder:
    """Count fallbacks and answers by `(site, kind)` and write them once, at process exit."""

    def __init__(self, *, directory: Path) -> None:
        self._directory: Path = directory
        self._counts: Counter[tuple[str, str]] = Counter()
        self._lock: threading.Lock = threading.Lock()
        _ = atexit.register(self.write)

    @classmethod
    def from_environment(cls) -> NativeFallbackRecorder | None:
        """Return a recorder when the debug record directory is set, otherwise None."""

        directory: str | None = os.environ.get(ANALYSIS_RECORD_DIR_ENV_VAR)
        return cls(directory=Path(directory)) if directory else None

    def record(self, *, site: str, kind: str, units: int = 1) -> None:
        """Count `units` fallbacks or answers at `site` of the sort `kind`."""

        with self._lock:
            self._counts[(site, kind)] += units

    def write(self) -> None:
        """Write the counts so far as `{"fallbacks": [[site, kind, count], ...]}`; none, no file."""

        with self._lock:
            counts: Counter[tuple[str, str]] = self._counts.copy()
        if not counts:
            return
        self._directory.mkdir(parents=True, exist_ok=True)
        rows: list[list[object]] = [
            [site, kind, count] for (site, kind), count in sorted(counts.items())
        ]
        target: Path = self._directory / f"{NATIVE_FALLBACK_RECORD_PREFIX}{os.getpid()}.json"
        _ = target.write_text(json.dumps({"fallbacks": rows}) + "\n", encoding="utf-8")
