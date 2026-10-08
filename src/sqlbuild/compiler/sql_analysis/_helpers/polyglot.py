"""Required Polyglot import helpers."""

from __future__ import annotations

import atexit
import inspect
import json
import os
import sys
import threading
from collections import Counter
from pathlib import Path
from typing import Any

import polyglot_sql

from sqlbuild.compiler.sql_analysis.constants import (
    ANALYSIS_RECORD_DIR_ENV_VAR,
    POLYGLOT_ANALYZE_QUERY_ENTRY_POINT,
    POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_COUNT,
    POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_INDEX,
    POLYGLOT_COMPLEXITY_GUARD_OPTION,
    POLYGLOT_COMPLEXITY_GUARD_PARAMETER,
    POLYGLOT_MAX_FUNCTION_CALL_DEPTH,
    POLYGLOT_MAX_FUNCTION_CALL_DEPTH_OPTION,
    POLYGLOT_SITE_RECORD_PREFIX,
)

_COMPLEXITY_GUARD: dict[str, int] = {
    POLYGLOT_MAX_FUNCTION_CALL_DEPTH_OPTION: POLYGLOT_MAX_FUNCTION_CALL_DEPTH,
}
_GUARDED_ENTRY_POINTS: frozenset[str] = frozenset(
    {
        POLYGLOT_ANALYZE_QUERY_ENTRY_POINT,
        "parse",
        "parse_data_type",
        "parse_one",
        "transpile",
        "validate",
        "validate_with_schema",
    }
)


class _GuardedEntryPoint:
    """One Polyglot entry point with SQLBuild's bounded trusted-SQL budget."""

    def __init__(self, *, name: str, function: Any) -> None:
        self._name: str = name
        self._function: Any = function

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self._has_explicit_options_guard(args=args, kwargs=kwargs):
            return self._function(*args, **kwargs)
        guarded_kwargs: dict[str, Any] = {
            POLYGLOT_COMPLEXITY_GUARD_PARAMETER: dict(_COMPLEXITY_GUARD),
            **kwargs,
        }
        return self._function(*args, **guarded_kwargs)

    def _has_explicit_options_guard(self, *, args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
        if self._name != POLYGLOT_ANALYZE_QUERY_ENTRY_POINT:
            return False
        options: object = kwargs.get("options")
        if len(args) >= POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_COUNT:
            options = args[POLYGLOT_ANALYZE_QUERY_OPTIONS_ARGUMENT_INDEX]
        return isinstance(options, dict) and POLYGLOT_COMPLEXITY_GUARD_OPTION in options


class _SiteRecorder:
    """Debug-only count of Polyglot wheel calls by calling `file:function`, written at exit."""

    def __init__(self, *, directory: Path) -> None:
        self._directory: Path = directory
        self._package_root: Path = Path(__file__).resolve().parents[3]
        self._calls: Counter[tuple[str, str]] = Counter()
        self._lock: threading.Lock = threading.Lock()
        _ = atexit.register(self._write)

    @classmethod
    def from_environment(cls) -> _SiteRecorder | None:
        """Return a recorder when the debug record directory is set, otherwise None."""

        directory: str | None = os.environ.get(ANALYSIS_RECORD_DIR_ENV_VAR)
        return cls(directory=Path(directory)) if directory else None

    def record(self, *, api: str, caller: Any) -> None:
        code: Any = caller.f_code
        path: Path = Path(code.co_filename).resolve()
        site: str = (
            path.relative_to(self._package_root).as_posix()
            if path.is_relative_to(self._package_root)
            else path.name
        )
        with self._lock:
            self._calls[(f"{site}:{code.co_qualname}", api)] += 1

    def _write(self) -> None:
        if not self._calls:
            return
        self._directory.mkdir(parents=True, exist_ok=True)
        rows: list[list[object]] = [
            [site, api, count] for (site, api), count in sorted(self._calls.items())
        ]
        target: Path = self._directory / f"{POLYGLOT_SITE_RECORD_PREFIX}{os.getpid()}.json"
        _ = target.write_text(json.dumps({"calls": rows}) + "\n", encoding="utf-8")


class _RecordedEntryPoint:
    """One Polyglot callable that records its calling site before running."""

    def __init__(self, *, name: str, function: Any, recorder: _SiteRecorder) -> None:
        self._name: str = name
        self._function: Any = function
        self._recorder: _SiteRecorder = recorder

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._recorder.record(api=self._name, caller=sys._getframe(1))
        return self._function(*args, **kwargs)


class _PolyglotSqlModule:
    """Proxy Polyglot parsing through SQLBuild's trusted-SQL policy."""

    def __init__(self, *, recorder: _SiteRecorder | None) -> None:
        self._recorder: _SiteRecorder | None = recorder

    def __getattr__(self, name: str) -> Any:
        attribute: Any = getattr(polyglot_sql, name)
        entry_point: Any = (
            _GuardedEntryPoint(name=name, function=attribute)
            if name in _GUARDED_ENTRY_POINTS
            else attribute
        )
        if self._recorder is None or not callable(attribute) or inspect.isclass(attribute):
            return entry_point
        return _RecordedEntryPoint(name=name, function=entry_point, recorder=self._recorder)


_POLYGLOT_SQL_MODULE: _PolyglotSqlModule = _PolyglotSqlModule(
    recorder=_SiteRecorder.from_environment()
)


def import_polyglot() -> Any:
    """Return SQLBuild's required Polyglot SQL module."""

    return _POLYGLOT_SQL_MODULE


def import_polyglot_sql() -> Any:
    """Return SQLBuild's required Polyglot SQL module."""

    return import_polyglot()


def is_polyglot_available() -> bool:
    """Return true because Polyglot SQL is a required dependency."""

    return True
